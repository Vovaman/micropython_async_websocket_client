import asyncio as a
import binascii
import random

try:
    from micropython import const, viper
except ImportError:
    viper = None

    def const(value):
        return value


# Opcodes
OP_CONT = const(0x0)
OP_TEXT = const(0x1)
OP_BYTES = const(0x2)
OP_CLOSE = const(0x8)
OP_PING = const(0x9)
OP_PONG = const(0xa)

# Close codes
CLOSE_OK = const(1000)
CLOSE_GOING_AWAY = const(1001)
CLOSE_PROTOCOL_ERROR = const(1002)
CLOSE_DATA_NOT_SUPPORTED = const(1003)
CLOSE_BAD_DATA = const(1007)
CLOSE_POLICY_VIOLATION = const(1008)
CLOSE_TOO_BIG = const(1009)
CLOSE_MISSING_EXTN = const(1010)
CLOSE_BAD_CONDITION = const(1011)

# A short write copies at most one chunk into the stream buffer.
_CHUNK = const(1024)
# Header and payload of a small frame go out in one write.
_ONE_WRITE = const(256)


def apply_mask(buf, mask, length):
    i = 0
    while i < length:
        buf[i] = buf[i] ^ mask[i & 3]
        i += 1


if viper is not None:
    try:
        @viper
        def _apply_mask(buf, mask, length: int):
            data = ptr8(buf)
            bits = ptr8(mask)
            i = 0
            while i < length:
                data[i] = data[i] ^ bits[i & 3]
                i += 1

        apply_mask = _apply_mask
    except Exception:
        pass


class _URI:
    __slots__ = ('protocol', 'hostname', 'port', 'path')

    def __init__(self, protocol, hostname, port, path):
        self.protocol = protocol
        self.hostname = hostname
        self.port = port
        self.path = path


def _frame_header(opcode, length):
    first = 0x80 | opcode
    if length < 126:
        return bytes((first, 0x80 | length))
    if length < 65536:
        return bytes((first, 0x80 | 126, (length >> 8) & 0xff, length & 0xff))
    return bytes((first, 0x80 | 127)) + length.to_bytes(8, 'big')


class AsyncWebsocketClient:
    def __init__(self, ms_delay_for_read=5):
        # Accepted so existing callers keep working. Reads wait on the socket.
        self.delay_read = ms_delay_for_read
        self._open = False
        self._stream = None
        self.sock = None
        self.uri = None
        self.max_size = None
        self._write_lock = None
        self._head = bytearray(2)
        self._ext = bytearray(8)
        self._mask_key = bytearray(4)

    async def _acquire_write(self):
        if self._write_lock is None:
            self._write_lock = a.Lock()
        await self._write_lock.acquire()

    async def open(self, new_val=None):
        if new_val is None:
            return self._open
        if new_val:
            self._open = True
            return True
        self._open = False
        stream = self._stream
        self._stream = None
        self.sock = None
        if stream is not None:
            await stream.wait_closed()
        return False

    async def close(self, code=None):
        if code is not None and self._open and self._stream is not None:
            try:
                await self.write_frame(OP_CLOSE, bytearray(code.to_bytes(2, 'big')))
            except Exception:
                pass
        return await self.open(False)

    def urlparse(self, uri):
        if uri.startswith('wss://'):
            protocol = 'wss'
            rest = uri[6:]
            port = 443
        elif uri.startswith('ws://'):
            protocol = 'ws'
            rest = uri[5:]
            port = 80
        else:
            raise ValueError('URL is invalid')
        slash = rest.find('/')
        if slash >= 0:
            hostport = rest[:slash]
            path = rest[slash:]
        else:
            hostport = rest
            path = None
        if not hostport:
            raise ValueError('URL is invalid')
        colon = hostport.rfind(':')
        if colon >= 0:
            host = hostport[:colon]
            port = int(hostport[colon + 1:])
        else:
            host = hostport
        if not host:
            raise ValueError('URL is invalid')
        return _URI(protocol, host, port, path)

    async def _connect(self, host, port, ssl_ctx):
        if ssl_ctx is None:
            return await a.open_connection(host, port)
        return await a.open_connection(
            host, port, ssl=ssl_ctx, server_hostname=host)

    def _make_ssl_context(self, keyfile, certfile, cafile, cert_reqs):
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if cert_reqs is None:
            cert_reqs = 0
        ctx.verify_mode = cert_reqs
        if certfile:
            ctx.load_cert_chain(certfile, keyfile)
        if cafile:
            with open(cafile, 'rb') as handle:
                ctx.load_verify_locations(cadata=handle.read())
        return ctx

    def _http_request(self, uri, headers, key):
        host = uri.hostname.encode('utf-8')
        port = str(uri.port).encode('utf-8')
        path = uri.path or '/'
        lines = (
            b'GET ' + path.encode('utf-8') + b' HTTP/1.1',
            b'Host: ' + host + b':' + port,
            b'Connection: Upgrade',
            b'Upgrade: websocket',
            b'Sec-WebSocket-Key: ' + key,
            b'Sec-WebSocket-Version: 13',
            b'Origin: http://' + host + b':' + port,
        )
        extra = []
        for name, value in headers or ():
            extra.append(
                str(name).encode('utf-8') + b': ' + str(value).encode('utf-8'))
        return b'\r\n'.join(lines + tuple(extra)) + b'\r\n\r\n'

    async def _write_all(self, buf):
        stream = self._stream
        view = memoryview(buf)
        offset = 0
        length = len(view)
        while offset < length:
            end = offset + _CHUNK
            if end > length:
                end = length
            stream.write(bytes(view[offset:end]))
            await stream.drain()
            offset = end

    async def _read_into_n(self, buf, length):
        view = memoryview(buf)
        offset = 0
        while offset < length:
            got = await self._stream.readinto(view[offset:length])
            if got is None:
                continue
            if got == 0:
                raise EOFError
            offset += got

    async def _read_exact(self, length):
        buf = bytearray(length)
        await self._read_into_n(buf, length)
        return buf

    async def a_readline(self):
        return await self._stream.readline()

    async def a_read(self, size=None):
        if not size:
            return b''
        return await self._read_exact(size)

    async def handshake(
            self, uri, headers=None, keyfile=None, certfile=None,
            cafile=None, cert_reqs=0):
        parsed = self.urlparse(uri)
        if self._stream is not None or self._open:
            await self.open(False)
        self.uri = parsed
        try:
            ssl_ctx = None
            if parsed.protocol == 'wss':
                ssl_ctx = self._make_ssl_context(
                    keyfile, certfile, cafile, cert_reqs)
            _reader, writer = await self._connect(
                parsed.hostname, parsed.port, ssl_ctx)
            self._stream = writer
            self.sock = getattr(writer, 's', None)
            key_raw = bytearray(16)
            index = 0
            while index < 16:
                key_raw[index] = random.getrandbits(8)
                index += 1
            key = binascii.b2a_base64(key_raw)[:-1]
            await self._write_all(self._http_request(parsed, headers, key))
            line = await self._stream.readline()
            header = line[:-2]
            if not header.startswith(b'HTTP/1.1 101 '):
                raise Exception(header)
            while header:
                line = await self._stream.readline()
                header = line[:-2]
        except Exception:
            try:
                await self.open(False)
            except Exception:
                pass
            raise
        return await self.open(True)

    async def read_frame(self, max_size=None):
        await self._read_into_n(self._head, 2)
        byte1 = self._head[0]
        byte2 = self._head[1]
        fin = bool(byte1 & 0x80)
        opcode = byte1 & 0x0f
        masked = bool(byte2 & 0x80)
        length = byte2 & 0x7f
        if length == 126:
            await self._read_into_n(self._ext, 2)
            length = (self._ext[0] << 8) | self._ext[1]
        elif length == 127:
            await self._read_into_n(self._ext, 8)
            # RFC 6455: the highest bit of a 64-bit length is reserved.
            if self._ext[0] & 0x80:
                await self.close(CLOSE_TOO_BIG)
                return True, OP_CLOSE, None
            length = int.from_bytes(self._ext, 'big')
        limit = self.max_size if max_size is None else max_size
        if limit is not None and length > limit:
            await self.close(CLOSE_TOO_BIG)
            return True, OP_CLOSE, None
        if masked:
            await self._read_into_n(self._mask_key, 4)
        if length:
            try:
                data = bytearray(length)
            except MemoryError:
                await self.close(CLOSE_TOO_BIG)
                return True, OP_CLOSE, None
            await self._read_into_n(data, length)
            if masked:
                apply_mask(data, self._mask_key, length)
        else:
            data = bytearray()
        return fin, opcode, data

    async def write_frame(self, opcode, data=b'', undo=False):
        if not isinstance(data, bytearray):
            data = bytearray(data)
            undo = False
        await self._acquire_write()
        try:
            mask_bits = random.getrandbits(32).to_bytes(4, 'big')
            apply_mask(data, mask_bits, len(data))
            try:
                prefix = _frame_header(opcode, len(data)) + mask_bits
                if len(data) <= _ONE_WRITE:
                    await self._write_all(prefix + data)
                else:
                    await self._write_all(prefix)
                    if data:
                        await self._write_all(data)
            finally:
                if undo:
                    apply_mask(data, mask_bits, len(data))
        finally:
            self._write_lock.release()

    def _payload_too_big(self, size):
        return self.max_size is not None and size > self.max_size

    async def recv(self):
        message = None
        message_op = None
        while self._open:
            try:
                fin, opcode, data = await self.read_frame(self.max_size)
            except Exception:
                await self.open(False)
                return None
            if opcode == OP_CLOSE or data is None:
                await self.open(False)
                return None
            if opcode == OP_PONG:
                continue
            if opcode == OP_PING:
                try:
                    await self.write_frame(OP_PONG, data)
                except Exception:
                    await self.open(False)
                    return None
                continue
            if opcode == OP_CONT:
                if message_op is None:
                    await self.close(CLOSE_PROTOCOL_ERROR)
                    return None
                if self._payload_too_big(len(message) + len(data)):
                    await self.close(CLOSE_TOO_BIG)
                    return None
                message.extend(data)
            elif opcode == OP_TEXT or opcode == OP_BYTES:
                if message_op is not None:
                    await self.close(CLOSE_PROTOCOL_ERROR)
                    return None
                message_op = opcode
                message = data
            else:
                raise ValueError(opcode)
            if fin:
                payload = message
                op = message_op
                message = None
                message_op = None
                if op == OP_TEXT:
                    return payload.decode('utf-8')
                return payload
        return None

    async def send(self, buf):
        if not self._open:
            return
        undo = False
        if isinstance(buf, str):
            opcode = OP_TEXT
            data = bytearray(buf.encode('utf-8'))
        elif isinstance(buf, bytearray):
            opcode = OP_BYTES
            data = buf
            undo = True
        elif isinstance(buf, bytes):
            opcode = OP_BYTES
            data = bytearray(buf)
        else:
            raise TypeError()
        await self.write_frame(opcode, data, undo)

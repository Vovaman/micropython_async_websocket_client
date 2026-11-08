import asyncio
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from async_websocket_client import ws as ws_mod
from async_websocket_client.ws import (
    CLOSE_PROTOCOL_ERROR,
    CLOSE_TOO_BIG,
    OP_BYTES,
    OP_CLOSE,
    OP_CONT,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    AsyncWebsocketClient,
)


def _run(coro):
    return asyncio.run(coro)


class FakeSocket:
    def __init__(self):
        self.incoming = bytearray()
        self.outgoing = bytearray()
        self.closed = False


class FakeStream:
    def __init__(self, sock, max_read=None):
        self.s = sock
        self.max_read = max_read

    async def readline(self):
        src = self.s.incoming
        nl = src.find(b'\n')
        if nl < 0:
            line = bytes(src)
            del src[:]
            return line
        line = bytes(src[:nl + 1])
        del src[:nl + 1]
        return line

    async def readinto(self, buf):
        src = self.s.incoming
        count = len(buf)
        if self.max_read is not None and count > self.max_read:
            count = self.max_read
        count = min(count, len(src))
        if count == 0:
            return 0
        buf[:count] = src[:count]
        del src[:count]
        return count

    def write(self, data):
        self.s.outgoing.extend(data)

    async def drain(self):
        await asyncio.sleep(0)

    async def wait_closed(self):
        self.s.closed = True


def _attach(payload=b'', max_read=None, max_size=None):
    sock = FakeSocket()
    sock.incoming.extend(payload)
    stream = FakeStream(sock, max_read=max_read)
    client = AsyncWebsocketClient(12)
    client._stream = stream
    client.sock = sock
    client._open = True
    client.max_size = max_size
    return client, sock


def server_frame(opcode, payload=b'', fin=True, mask=None):
    first = (0x80 if fin else 0) | opcode
    length = len(payload)
    if length < 126:
        header = bytes((first, (0x80 if mask else 0) | length))
    elif length < 65536:
        header = bytes((
            first, (0x80 if mask else 0) | 126,
            (length >> 8) & 0xff, length & 0xff))
    else:
        header = bytes((first, (0x80 if mask else 0) | 127)) + length.to_bytes(8, 'big')
    body = bytearray(payload)
    if mask:
        index = 0
        while index < len(body):
            body[index] ^= mask[index & 3]
            index += 1
        return header + mask + body
    return header + body


def parse_frames(buf):
    frames = []
    index = 0
    while index + 2 <= len(buf):
        first = buf[index]
        second = buf[index + 1]
        index += 2
        if not (second & 0x80):
            raise AssertionError('client frame is not masked')
        length = second & 0x7f
        if length == 126:
            length = int.from_bytes(buf[index:index + 2], 'big')
            index += 2
        elif length == 127:
            length = int.from_bytes(buf[index:index + 8], 'big')
            index += 8
        mask = buf[index:index + 4]
        index += 4
        raw = bytearray(buf[index:index + length])
        index += length
        pos = 0
        while pos < len(raw):
            raw[pos] ^= mask[pos & 3]
            pos += 1
        frames.append((bool(first & 0x80), first & 0x0f, bytes(raw)))
    return frames


class UrlParseTests(unittest.TestCase):
    def test_ws_defaults(self):
        uri = AsyncWebsocketClient().urlparse('ws://example.com')
        self.assertEqual(uri.protocol, 'ws')
        self.assertEqual(uri.hostname, 'example.com')
        self.assertEqual(uri.port, 80)
        self.assertIsNone(uri.path)

    def test_ws_port_and_query(self):
        uri = AsyncWebsocketClient().urlparse('ws://192.168.0.1:8080/ws?x=1')
        self.assertEqual(uri.port, 8080)
        self.assertEqual(uri.path, '/ws?x=1')

    def test_wss_default_port(self):
        uri = AsyncWebsocketClient().urlparse('wss://example.com/a/b')
        self.assertEqual(uri.protocol, 'wss')
        self.assertEqual(uri.port, 443)
        self.assertEqual(uri.path, '/a/b')

    def test_invalid_scheme(self):
        with self.assertRaises(ValueError):
            AsyncWebsocketClient().urlparse('http://example.com')

    def test_missing_host(self):
        with self.assertRaises(ValueError):
            AsyncWebsocketClient().urlparse('ws://')


class MaskTests(unittest.TestCase):
    def test_apply_mask_roundtrip(self):
        buf = bytearray(b'hello')
        mask = b'\x01\x02\x03\x04'
        ws_mod.apply_mask(buf, mask, len(buf))
        self.assertEqual(bytes(buf), bytes(b ^ mask[i & 3] for i, b in enumerate(b'hello')))
        ws_mod.apply_mask(buf, mask, len(buf))
        self.assertEqual(buf, bytearray(b'hello'))


class FrameTests(unittest.TestCase):
    def test_recv_text_from_one_byte_reads(self):
        frame = server_frame(OP_TEXT, b'OK')

        async def scenario():
            client, _sock = _attach(frame, max_read=1)
            self.assertEqual(client.delay_read, 12)
            return await client.recv()

        self.assertEqual(_run(scenario()), 'OK')

    def test_recv_binary_and_masked_server_frame(self):
        frame = server_frame(OP_BYTES, b'\x00\xff', mask=b'\xaa\xbb\xcc\xdd')

        async def scenario():
            client, _sock = _attach(frame)
            data = await client.recv()
            return data

        data = _run(scenario())
        self.assertIsInstance(data, bytearray)
        self.assertEqual(data, b'\x00\xff')

    def test_extended_lengths(self):
        medium = server_frame(OP_BYTES, b'x' * 200)
        huge = server_frame(OP_BYTES, b'y' * 65536)

        async def scenario():
            client, _sock = _attach(medium + huge, max_read=3)
            first = await client.recv()
            second = await client.recv()
            return first, second

        first, second = _run(scenario())
        self.assertEqual(first, b'x' * 200)
        self.assertEqual(second, b'y' * 65536)

    def test_fragments_with_ping_between(self):
        text = 'é'.encode('utf-8')
        incoming = b''.join((
            server_frame(OP_TEXT, text[:1], fin=False),
            server_frame(OP_PING, b'xyz'),
            server_frame(OP_CONT, text[1:]),
        ))

        async def scenario():
            client, sock = _attach(incoming)
            message = await client.recv()
            return message, parse_frames(sock.outgoing)

        message, frames = _run(scenario())
        self.assertEqual(message, 'é')
        self.assertEqual(frames, [(True, OP_PONG, b'xyz')])

    def test_pong_is_ignored(self):
        incoming = server_frame(OP_PONG, b'nope') + server_frame(OP_TEXT, b'yes')

        async def scenario():
            client, sock = _attach(incoming)
            message = await client.recv()
            return message, sock.outgoing

        message, outgoing = _run(scenario())
        self.assertEqual(message, 'yes')
        self.assertEqual(outgoing, b'')

    def test_close_from_server(self):
        async def scenario():
            client, _sock = _attach(server_frame(OP_CLOSE, b'\x03\xe8'))
            message = await client.recv()
            return message, await client.open()

        message, opened = _run(scenario())
        self.assertIsNone(message)
        self.assertFalse(opened)

    def test_leading_continuation_closes(self):
        async def scenario():
            client, sock = _attach(server_frame(OP_CONT, b'x'))
            message = await client.recv()
            return message, await client.open(), parse_frames(sock.outgoing)

        message, opened, frames = _run(scenario())
        self.assertIsNone(message)
        self.assertFalse(opened)
        self.assertEqual(frames[0][1], OP_CLOSE)
        self.assertEqual(
            int.from_bytes(frames[0][2], 'big'), CLOSE_PROTOCOL_ERROR)

    def test_new_data_frame_during_fragment_closes(self):
        incoming = server_frame(OP_TEXT, b'ab', fin=False) + server_frame(OP_TEXT, b'cd')

        async def scenario():
            client, sock = _attach(incoming)
            message = await client.recv()
            return message, parse_frames(sock.outgoing)

        message, frames = _run(scenario())
        self.assertIsNone(message)
        self.assertEqual(
            int.from_bytes(frames[0][2], 'big'), CLOSE_PROTOCOL_ERROR)

    def test_fragment_sum_over_max_size(self):
        incoming = (
            server_frame(OP_BYTES, b'abc', fin=False)
            + server_frame(OP_CONT, b'def'))

        async def scenario():
            client, sock = _attach(incoming, max_size=5)
            message = await client.recv()
            return message, parse_frames(sock.outgoing)

        message, frames = _run(scenario())
        self.assertIsNone(message)
        self.assertEqual(int.from_bytes(frames[0][2], 'big'), CLOSE_TOO_BIG)

    def test_reserved_length_bit_closes(self):
        frame = bytes((0x82, 127, 0x80, 0, 0, 0, 0, 0, 0, 0))

        async def scenario():
            client, sock = _attach(frame)
            message = await client.recv()
            return message, parse_frames(sock.outgoing)

        message, frames = _run(scenario())
        self.assertIsNone(message)
        self.assertEqual(int.from_bytes(frames[0][2], 'big'), CLOSE_TOO_BIG)

    def test_single_frame_over_max_size_does_not_read_body(self):
        header = bytes((0x82, 50))

        async def scenario():
            client, sock = _attach(header, max_size=10)
            message = await client.recv()
            return message, sock.closed, parse_frames(sock.outgoing)

        message, closed, frames = _run(scenario())
        self.assertIsNone(message)
        self.assertTrue(closed)
        self.assertEqual(int.from_bytes(frames[0][2], 'big'), CLOSE_TOO_BIG)

    def test_unknown_opcode_raises(self):
        async def scenario():
            client, _sock = _attach(bytes((0x83, 0)))
            await client.recv()

        with self.assertRaises(ValueError):
            _run(scenario())

    def test_eof_closes(self):
        async def scenario():
            client, sock = _attach(b'')
            message = await client.recv()
            return message, sock.closed

        message, closed = _run(scenario())
        self.assertIsNone(message)
        self.assertTrue(closed)


class SendTests(unittest.TestCase):
    def setUp(self):
        self._bits = ws_mod.random.getrandbits
        ws_mod.random.getrandbits = lambda _n: 0x01020304

    def tearDown(self):
        ws_mod.random.getrandbits = self._bits

    def test_send_text_is_masked(self):
        async def scenario():
            client, sock = _attach()
            await client.send('A')
            return bytes(sock.outgoing)

        self.assertEqual(
            _run(scenario()),
            bytes((0x81, 0x81, 0x01, 0x02, 0x03, 0x04, 0x40)))

    def test_send_binary_extended_length(self):
        payload = b'z' * 300

        async def scenario():
            client, sock = _attach()
            await client.send(payload)
            return parse_frames(sock.outgoing)

        frames = _run(scenario())
        self.assertEqual(frames, [(True, OP_BYTES, payload)])

    def test_send_64bit_length(self):
        payload = b'q' * 65536

        async def scenario():
            client, sock = _attach()
            await client.send(payload)
            return parse_frames(sock.outgoing)

        frames = _run(scenario())
        self.assertEqual(frames, [(True, OP_BYTES, payload)])

    def test_send_restores_bytearray(self):
        payload = bytearray(b'image')

        async def scenario():
            client, sock = _attach()
            await client.send(payload)
            return bytes(payload), parse_frames(sock.outgoing)

        restored, frames = _run(scenario())
        self.assertEqual(restored, b'image')
        self.assertEqual(frames, [(True, OP_BYTES, b'image')])

    def test_send_when_closed_writes_nothing(self):
        async def scenario():
            client, sock = _attach()
            await client.open(False)
            await client.send('nope')
            return sock.outgoing

        self.assertEqual(_run(scenario()), b'')

    def test_send_rejects_other_types(self):
        async def scenario():
            client, _sock = _attach()
            await client.send(1)

        with self.assertRaises(TypeError):
            _run(scenario())

    def test_concurrent_sends_stay_whole_frames(self):
        async def scenario():
            client, sock = _attach()

            async def second():
                await asyncio.sleep(0)
                await client.send('BBBB')

            await asyncio.gather(second(), client.send('AAAA'))
            return parse_frames(sock.outgoing)

        frames = _run(scenario())
        self.assertEqual(
            [item[2] for item in frames], [b'AAAA', b'BBBB'])
        self.assertTrue(all(item[0] and item[1] == OP_TEXT for item in frames))


class HandshakeTests(unittest.TestCase):
    def _client(self, response, max_read=None):
        sock = FakeSocket()
        sock.incoming.extend(response)
        stream = FakeStream(sock, max_read=max_read)
        client = AsyncWebsocketClient()
        calls = []

        async def connect(host, port, ssl_ctx):
            calls.append((host, port, ssl_ctx))
            return stream, stream

        client._connect = connect
        return client, sock, calls

    def test_ws_request(self):
        response = (
            b'HTTP/1.1 101 Switching Protocols\r\n'
            b'Upgrade: websocket\r\n'
            b'\r\n')

        async def scenario():
            client, sock, calls = self._client(response, max_read=5)
            opened = await client.handshake(
                'ws://example.com:9000/socket',
                headers=[('Authorization', 'Bearer t')])
            return opened, calls, bytes(sock.outgoing), await client.open()

        opened, calls, request, flag = _run(scenario())
        self.assertTrue(opened)
        self.assertTrue(flag)
        self.assertEqual(calls, [('example.com', 9000, None)])
        self.assertIn(b'GET /socket HTTP/1.1\r\n', request)
        self.assertIn(b'Host: example.com:9000\r\n', request)
        self.assertIn(b'Connection: Upgrade\r\n', request)
        self.assertIn(b'Upgrade: websocket\r\n', request)
        self.assertIn(b'Sec-WebSocket-Version: 13\r\n', request)
        self.assertIn(b'Origin: http://example.com:9000\r\n', request)
        self.assertIn(b'Authorization: Bearer t\r\n', request)
        self.assertTrue(request.endswith(b'\r\n\r\n'))
        key_line = [
            line for line in request.split(b'\r\n')
            if line.startswith(b'Sec-WebSocket-Key: ')][0]
        key = key_line.split(b': ', 1)[1]
        self.assertEqual(len(key), 24)

    def test_bad_status_closes(self):
        async def scenario():
            client, sock, _calls = self._client(b'HTTP/1.1 500 Nope\r\n\r\n')
            with self.assertRaises(Exception) as caught:
                await client.handshake('ws://example.com/ws')
            return caught.exception, await client.open(), sock.closed

        error, opened, closed = _run(scenario())
        self.assertTrue(error.args[0].startswith(b'HTTP/1.1 500'))
        self.assertFalse(opened)
        self.assertTrue(closed)

    def test_invalid_url_does_not_connect(self):
        async def scenario():
            client = AsyncWebsocketClient()
            called = []

            async def connect(*args):
                called.append(args)

            client._connect = connect
            with self.assertRaises(ValueError):
                await client.handshake('tcp://example.com')
            return called

        self.assertEqual(_run(scenario()), [])

    def test_wss_builds_context_without_touching_plain_ws(self):
        class Ctx:
            def __init__(self, protocol):
                self.protocol = protocol
                self.verify_mode = None
                self.chain = None
                self.cadata = None

            def load_cert_chain(self, certfile, keyfile=None):
                self.chain = (certfile, keyfile)

            def load_verify_locations(self, cadata=None):
                self.cadata = cadata

        fake_ssl = types.SimpleNamespace(
            PROTOCOL_TLS_CLIENT=7,
            SSLContext=Ctx,
        )
        response = b'HTTP/1.1 101 Switching Protocols\r\n\r\n'

        async def scenario(ca_path):
            client, _sock, calls = self._client(response)
            real = sys.modules.get('ssl')
            sys.modules['ssl'] = fake_ssl
            try:
                await client.handshake(
                    'wss://secure.example/ws',
                    certfile='cert.pem',
                    keyfile='key.pem',
                    cafile=ca_path,
                    cert_reqs=2)
            finally:
                if real is None:
                    sys.modules.pop('ssl', None)
                else:
                    sys.modules['ssl'] = real
            return calls

        with tempfile.NamedTemporaryFile() as handle:
            handle.write(b'CA')
            handle.flush()
            calls = _run(scenario(handle.name))
        ctx = calls[0][2]
        self.assertEqual(calls[0][0], 'secure.example')
        self.assertEqual(calls[0][1], 443)
        self.assertEqual(ctx.protocol, 7)
        self.assertEqual(ctx.verify_mode, 2)
        self.assertEqual(ctx.chain, ('cert.pem', 'key.pem'))
        self.assertEqual(ctx.cadata, b'CA')

    def test_plain_ws_does_not_import_ssl(self):
        async def scenario():
            client, _sock, calls = self._client(
                b'HTTP/1.1 101 Switching Protocols\r\n\r\n')
            real = sys.modules.get('ssl')
            sys.modules['ssl'] = None
            try:
                await client.handshake('ws://example.com/ws')
            finally:
                if real is None:
                    sys.modules.pop('ssl', None)
                else:
                    sys.modules['ssl'] = real
            return calls

        calls = _run(scenario())
        self.assertIsNone(calls[0][2])


class CompatReadTests(unittest.TestCase):
    def test_a_read_assembles_chunks(self):
        async def scenario():
            client, _sock = _attach(b'abcdef', max_read=2)
            return bytes(await client.a_read(5))

        self.assertEqual(_run(scenario()), b'abcde')

    def test_a_read_zero(self):
        async def scenario():
            client, _sock = _attach(b'abcdef')
            return await client.a_read(0)

        self.assertEqual(_run(scenario()), b'')

    def test_a_readline(self):
        async def scenario():
            client, _sock = _attach(b'one\r\ntwo\r\n')
            return await client.a_readline(), await client.a_readline()

        self.assertEqual(_run(scenario()), (b'one\r\n', b'two\r\n'))


if __name__ == '__main__':
    unittest.main()

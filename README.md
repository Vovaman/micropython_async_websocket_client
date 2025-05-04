> This module is only for [micropython](https://micropython.org/)!

# micropython-async_websocket_client
This module is designed for ESP32 (and other) controllers.

Target: create and keep alive connection channel with websocket server.

You may send captured data from controlled devices through this channel to server and accept managing signals on your controller.

This data channel works as background task while main control cycle is running too.
The break of websocket channel doesn't corrupt main cycle of control.

Module supports TLS with both client and server certificates.

This project based on:

https://github.com/danni/uwebsockets

https://github.com/peterhinch/micropython-async

**My gratitudes to authors**.

# requirements
This module is designed and tested on [ESP32S-WROOM-32](https://ru.wikipedia.org/wiki/%D0%A4%D0%B0%D0%B9%D0%BB:ESP32_Espressif_ESP-WROOM-32_Dev_Board.jpg).

Development and tests were done based on [ESP32-20250415-v1.25.0.bin](https://micropython.org/resources/firmware/ESP32_GENERIC-20250415-v1.25.0.bin).

# installation
## Through network
<details>
    <summary>Run this commands on your controller:</summary>

    You have to reflash your board with [micropython](https://micropython.org/).
    Details are explained in https://github.com/Vovaman/start_ESP32_with_micropython.
    You may use VSCode as explained in link above or use `picocom` tool (also explained) to connect your board and run python console (REPL) on it.
    So, after you are in your board...
</details>

```python
>>> import network
>>> wifi = network.WLAN(network.STA_IF)
>>> wifi.active(1)
>>> wifi.connect(<name_of_your_wifi_net>, <wifi_password>)
>>> import mip
>>> mip.install("github:Vovaman/micropython_async_websocket_client/async_websocket_client/ws.py")
```

## Manually
You have just copy ``ws.py`` file to ``/lib`` folder in controller.

Example with ``mpremote``:

```bash
$ mpremote fs mkdir /lib
$ mpremote fs cp async_websocket_client/ws.py :/lib/
```

All needed dependencies are in firmware.

# example
An example of how to use this module can be found in the https://github.com/Vovaman/example_async_websocket.

Use this example instead of documentation.

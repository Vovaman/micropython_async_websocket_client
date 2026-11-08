[![License Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
![MicroPython 1.25+](https://img.shields.io/badge/MicroPython-1.25%2B-green.svg)
![ESP32](https://img.shields.io/badge/ESP32-supported-blue.svg)
[![PyPI](https://img.shields.io/pypi/v/micropython-async_websocket_client.svg)](https://pypi.org/project/micropython-async_websocket_client/)

> This module is only for [MicroPython](https://micropython.org/)!

# micropython-async_websocket_client

This module is designed for the ESP32 and other microcontrollers.

It keeps a WebSocket connection to a server alive. You can send captured data from the attached devices to the server and receive control signals on the controller.

The channel runs as a background task while the main control loop is running. A dropped WebSocket connection does not stop that loop.

The module supports TLS with both client and server certificates.

This project is based on:

https://github.com/danni/uwebsockets

https://github.com/peterhinch/micropython-async

**Thanks to the authors.**

# Requirements

The module is designed and tested on the [ESP32-WROOM-32](https://ru.wikipedia.org/wiki/%D0%A4%D0%B0%D0%B9%D0%BB:ESP32_Espressif_ESP-WROOM-32_Dev_Board.jpg).

Development and tests on the device were done with [ESP32-20250415-v1.25.0.bin](https://micropython.org/resources/firmware/ESP32_GENERIC-20250415-v1.25.0.bin).

The constructor still accepts `ms_delay_for_read`, so existing callers keep working. Socket reads wait until the controller reports data instead of sleeping for that interval.

# Installation

## Over the network

<details>
    <summary>Prepare the board, then run the commands below on it.</summary>

    Flash the board with [MicroPython](https://micropython.org/).
    The steps are described in https://github.com/Vovaman/start_ESP32_with_micropython.
    You can use VS Code, as explained in that repository, or `picocom` to open the Python console (REPL).
</details>

```python
>>> import network
>>> wifi = network.WLAN(network.STA_IF)
>>> wifi.active(1)
>>> wifi.connect("wifi_name", "wifi_password")
>>> import mip
>>> mip.install("github:Vovaman/micropython_async_websocket_client/async_websocket_client/ws.py")
```

## Manually

Copy `ws.py` to the `/lib` directory on the controller.

Example with `mpremote`:

```bash
$ mpremote fs mkdir /lib
$ mpremote fs cp async_websocket_client/ws.py :/lib/
```

If `/lib` already exists, skip `mkdir`. All required dependencies are included in the firmware.

# Example

A usage example is at https://github.com/Vovaman/example_async_websocket.

Use that example as the documentation.

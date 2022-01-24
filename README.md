# micropython-async_websocket_client
This module is designed for ESP32 (and other) controllers.  
Goal: create and keep alive connection channel with websocket server.   
You may send captured data from controlled devices through this channel to server and accept managing signals on your controller.  
This data channel works as background task while main control cycle is running too.  
The break of websocket channel doesn't corrupt main cycle of control.

This project based on:  
https://github.com/danni/uwebsockets  
https://github.com/peterhinch/micropython-async

**My gratitudes to authors**.

# requirements
This module is designed and tested on [ESP32S-WROOM-32](https://ru.wikipedia.org/wiki/%D0%A4%D0%B0%D0%B9%D0%BB:ESP32_Espressif_ESP-WROOM-32_Dev_Board.jpg).  
Development and tests were done based on [esp32-20220117-v1.18.bin](https://micropython.org/resources/firmware/esp32-20220117-v1.18.bin).  

# installation
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
>>> import upip
>>> upip.install('micropython_async_websocket_client')
```

All needed dependencies are in esp32-20220117-v1.18.bin.
# example
Sample using of this module is in https://github.com/Vovaman/example_async_websocket.

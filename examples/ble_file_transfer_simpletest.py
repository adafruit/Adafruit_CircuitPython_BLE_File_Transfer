# SPDX-FileCopyrightText: 2020 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Used with ble_uart_echo_test.py. Transmits "echo" to the UARTService and receives it back.
"""

import time

from adafruit_ble import BLERadio
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
import adafruit_ble_file_transfer

ble = BLERadio()
# ble._adapter.erase_bonding()
while True:
    try:
        while ble.connected and any(
            adafruit_ble_file_transfer.FileTransferService in connection for connection in ble.connections
        ):
            for connection in ble.connections:
                if adafruit_ble_file_transfer.FileTransferService not in connection:
                    continue
                if not connection.paired:
                    connection.pair()
                print("echo")
                service = connection[adafruit_ble_file_transfer.FileTransferService]
                client = adafruit_ble_file_transfer.FileTransferClient(service)
                client.write("/hello.txt", "Hello world".encode("utf-8"))
                c = client.read("/hello.txt")
                print(c)
                client.mkdir("/world/")
                print(client.listdir("/world/"))
                client.write("/world/hello.txt", "Hi world".encode("utf-8"))
                print(client.listdir("/world/"))
            time.sleep(5)
    except ConnectionError:
        pass

    print("disconnected, scanning")
    for advertisement in ble.start_scan(ProvideServicesAdvertisement, timeout=1):
        if adafruit_ble_file_transfer.FileTransferService not in advertisement.services:
            continue
        ble.connect(advertisement)
        print("connected")
        break
    ble.stop_scan()

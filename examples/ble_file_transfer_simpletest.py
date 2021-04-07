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
            adafruit_ble_file_transfer.FileTransferService in connection
            for connection in ble.connections
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
                client.write("/world/hi.txt", "Hi world".encode("utf-8"))
                client.write("/world/hello.txt", "Hello world".encode("utf-8"))
                c = client.read("/world/hello.txt")
                print(c)
                print(client.listdir("/world/"))
                client.delete("/world/hello.txt")
                try:
                    client.delete("/world/")  # should raise an exception
                except ValueError:
                    print("exception correctly raised")
                print(client.listdir("/world/"))
                client.delete("/world/hi.txt")
                client.delete("/world/")
                print(client.listdir("/"))
            time.sleep(20)
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

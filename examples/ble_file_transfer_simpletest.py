# SPDX-FileCopyrightText: 2020 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Used with ble_uart_echo_test.py. Transmits "echo" to the UARTService and receives it back.
"""

import random
import time

from adafruit_ble import BLERadio
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
import adafruit_ble_file_transfer


def _write(client, filename, contents, *, offset=0):
    start = time.monotonic()
    client.write(filename, contents, offset=offset)
    duration = time.monotonic() - start
    print("wrote", filename, "at rate", len(contents) / duration, "B/s")


def _read(client, filename, *, offset=0):
    start = time.monotonic()
    contents = client.read(filename, offset=offset)
    duration = time.monotonic() - start
    print("read", filename, "at rate", len(contents) / duration, "B/s")
    return contents


ble = BLERadio()
# ble._adapter.erase_bonding()
# print("erased")
while True:
    try:
        while ble.connected:
            print("connnnnneeeected")
            for connection in ble.connections:
                print(
                    "services", connection._bleio_connection.discover_remote_services()
                )
                if adafruit_ble_file_transfer.FileTransferService not in connection:
                    continue
                if not connection.paired:
                    print("pairing")
                    connection.pair()
                print("connecteeeeeddd")
                service = connection[adafruit_ble_file_transfer.FileTransferService]
                client = adafruit_ble_file_transfer.FileTransferClient(service)
                _write(client, "/hello.txt", "Hello world".encode("utf-8"))
                print("write sent")
                c = _read(client, "/hello.txt")
                print(len(c), c)
                client.mkdir("/world/")
                print(client.listdir("/world/"))
                _write(client, "/world/hi.txt", "Hi world".encode("utf-8"))

                hello_world = "Hello world".encode("utf-8")
                _write(client, "/world/hello.txt", hello_world)
                c = _read(client, "/world/hello.txt")
                print(c)

                # Test offsets
                hello = len("Hello ".encode("utf-8"))
                c = _read(client, "/world/hello.txt", offset=hello)
                print(c)

                _write(client, "/world/hello.txt", "offsets!", offset=hello)
                c = _read(client, "/world/hello.txt", offset=0)
                print(c)

                # Test deleting
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

                large_1k = bytearray(1024)
                for i in range(len(large_1k)):
                    large_1k[i] = random.randint(0, 255)
                _write(client, "/random.txt", large_1k)
                time.sleep(0.1)
                contents = _read(client, "/random.txt")
                if large_1k != contents:
                    print("large contents don't match!")
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

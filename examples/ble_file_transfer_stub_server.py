# SPDX-FileCopyrightText: Copyright (c) 2021 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: Unlicense

"""This example broadcasts out the creation id based on the CircuitPython machine
   string."""

import adafruit_ble_file_transfer
from adafruit_ble_file_transfer import FileTransferService
import adafruit_ble_creation
import adafruit_ble
import struct
import time
import os

cid = adafruit_ble_creation.creation_ids[os.uname().machine]

ble = adafruit_ble.BLERadio()

service = FileTransferService()
print(ble.name)
advert = adafruit_ble_creation.Creation(creation_id=cid, services=[service])
print(bytes(advert), len(bytes(advert)))

stored_data = {}

packet_buffer = bytearray(256)
out_buffer = bytearray(256)
while True:
    ble.start_advertising(advert)
    while not ble.connected:
        pass
    print(ble.connected, ble.connections)
    while ble.connected:
        psize = service.raw.incoming_packet_length
        if psize > len(packet_buffer):
            packet_buffer = bytearray(psize)
        read = service.raw.readinto(packet_buffer)
        if read == 0:
            continue
        p = packet_buffer[:read]
        command = struct.unpack_from(">B", p)[0]
        if command == FileTransferService.WRITE:
            content_length, path_length = struct.unpack_from(">IH", p, offset=1)
            path_start = struct.calcsize(">BIH")
            path = str(p[path_start:path_start+path_length], "utf-8")
            contents_read = 0
            contents = bytearray(content_length)
            print("write", content_length, path)
            while contents_read < content_length:
                next_amount = min(10, content_length - contents_read)
                #print(FileTransferService.WRITE, FileTransferService.OK)
                service.raw.write(struct.pack(">BBI", FileTransferService.WRITE, FileTransferService.OK, next_amount))
                read = service.raw.readinto(packet_buffer)
                while read == 0:
                    read = service.raw.readinto(packet_buffer)
                contents[contents_read:contents_read+read] = packet_buffer[:read]
                contents_read += read
                #print(read, packet_buffer[:read])
            stored_data[path] = contents

        elif command == adafruit_ble_file_transfer.FileTransferService.READ:
            free_space, path_length = struct.unpack_from(">IH", p, offset=1)
            path_start = struct.calcsize(">BIH")
            path = str(p[path_start:path_start+path_length], "utf-8")
            print("read", path)
            # contents_read = 0
            # contents = bytearray(content_length)
            # print("write", content_length, path)
            # while contents_read < content_length:
            #     next_amount = min(10, content_length - contents_read)
            #     #print(FileTransferService.WRITE, FileTransferService.OK)
            #     service.raw.write(struct.pack(">BBI", FileTransferService.WRITE, FileTransferService.OK, next_amount))
            #     read = service.raw.readinto(packet_buffer)
            #     while read == 0:
            #         read = service.raw.readinto(packet_buffer)
            #     contents[contents_read:contents_read+read] = packet_buffer[:read]
            #     contents_read += read
            #     #print(read, packet_buffer[:read])
            # stored_data[path] = contents
        else:
            print("unknown command", command)
    print("disconnected")


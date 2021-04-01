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

def find_dir(path):
    pieces = path.split("/")
    parent = stored_data
    i = 1
    while i < len(pieces) - 1:
        piece = pieces[i]
        if piece not in parent:
            return None
        parent = piece
        i += 1
    return parent

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
            print(path.split("/"))
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
            d = find_dir(path)
            if path not in d:
                print("missing path")
                service.raw.write(struct.pack(">BBB", FileTransferService.READ, FileTransferService.ERR, FileTransferService.ERR_NO_FILE))
                continue

            contents_sent = 0
            contents = stored_data[path]
            while contents_sent < len(contents):
                remaining = len(contents) - contents_sent
                next_amount = min(remaining, free_space)
                print("sending", next_amount)
                header = struct.pack(">BBII", FileTransferService.WRITE, FileTransferService.OK, len(contents), next_amount)
                service.raw.write(header + contents[contents_sent:contents_sent + next_amount])
                contents_sent += next_amount

                # Wait for the next free amount even if we've sent everything. A 0 free reply can
                # confirm everything worked.
                read = service.raw.readinto(packet_buffer)
                while read == 0:
                    read = service.raw.readinto(packet_buffer)
                confirm, status, free_space = struct.unpack_from(">BBI", p)
        elif command == adafruit_ble_file_transfer.FileTransferService.MKDIR:
            path_length = struct.unpack_from(">H", p, offset=1)[0]
            path_start = struct.calcsize(">BH")
            path = str(p[path_start:path_start+path_length], "utf-8")
            print("mkdir", path)
            pieces = path.split("/")
            parent = stored_data
            i = 1
            ok = True
            while i < len(pieces) - 1 and ok:
                piece = pieces[i]
                if piece not in parent:
                    parent[piece] = {}
                elif not isinstance(parent[piece], dict):
                    ok = False
                parent = piece
                i += 1
            
            if ok:
                header = struct.pack(">BB", FileTransferService.WRITE, FileTransferService.OK)
            else:
                header = struct.pack(">BB", FileTransferService.WRITE, FileTransferService.ERR)
            service.raw.write(header)
        else:
            print("unknown command", command)
    print("disconnected")


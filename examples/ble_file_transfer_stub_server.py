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
        parent = parent[piece]
        i += 1
    return parent

def read_packets(buf, *, target_size=None):
    if not target_size:
        target_size = len(buf)
    total_read = 0
    buf = memoryview(buf)
    while total_read < target_size:
        read = service.raw.readinto(buf[total_read:])
        total_read += read

    return read

def write_packets(buf):
    service.raw.write(buf)

def read_complete_path(starting_path, total_length):
    path = bytearray(total_length)
    current_path_length = len(starting_path)
    remaining_path = total_length - current_path_length
    path[:current_path_length] = starting_path
    if remaining_path > 0:
        read_packets(memoryview(path)[current_path_length:], target_size=remaining_path)
    return str(path, "utf-8")

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
            path = read_complete_path(p[path_start:], path_length)
            contents_read = 0
            contents = bytearray(content_length)
            d = find_dir(path)
            filename = path.split("/")[-1]
            while contents_read < content_length:
                next_amount = min(10, content_length - contents_read)
                header = struct.pack(">BBI", FileTransferService.WRITE, FileTransferService.OK, next_amount)
                write_packets(header)
                read = read_packets(packet_buffer, target_size=next_amount)
                contents[contents_read:contents_read+read] = packet_buffer[:read]
                contents_read += read
            d[filename] = contents

        elif command == adafruit_ble_file_transfer.FileTransferService.READ:
            free_space, path_length = struct.unpack_from(">IH", p, offset=1)
            path_start = struct.calcsize(">BIH")
            path = read_complete_path(p[path_start:], path_length)
            d = find_dir(path)
            filename = path.split("/")[-1]
            if filename not in d:
                print("missing path")
                error_response = struct.pack(">BBII", FileTransferService.READ, FileTransferService.ERR, 0, 0)
                write_packets(error_response)
                continue

            contents_sent = 0
            contents = d[filename]
            while contents_sent < len(contents):
                remaining = len(contents) - contents_sent
                next_amount = min(remaining, free_space)
                header = struct.pack(">BBII", FileTransferService.READ, FileTransferService.OK, len(contents), next_amount)
                write_packets(header + contents[contents_sent:contents_sent + next_amount])
                contents_sent += next_amount

                read = read_packets(packet_buffer, target_size=struct.calcsize(">BBI"))
                confirm, status, free_space = struct.unpack_from(">BBI", p)
        elif command == adafruit_ble_file_transfer.FileTransferService.MKDIR:
            path_length = struct.unpack_from(">H", p, offset=1)[0]
            path_start = struct.calcsize(">BH")
            path = read_complete_path(p[path_start:], path_length)
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
            write_packets(header)
        elif command == adafruit_ble_file_transfer.FileTransferService.LISTDIR:
            path_length = struct.unpack_from(">H", p, offset=1)[0]
            path_start = struct.calcsize(">BH")
            path = read_complete_path(p[path_start:], path_length)

            # cmd, status, i, total, flags, file_size, path_length = struct.unpack(">BBIIBIH", b)

            d = find_dir(path)
            if d is None:
                error = struct.pack(">BBIIBIH", FileTransferService.WRITE, FileTransferService.ERR, 0, 0, 0, 0, 0)
                write_packets(error)

            filenames = sorted(d.keys())
            total_files = len(filenames)
            for i, filename in enumerate(filenames):
                encoded_filename = filename.encode("utf-8")
                flags = 0
                contents = d[filename]
                if isinstance(contents, dict):
                    flags = FileTransferService.DIRECTORY
                else:
                    content_length = len(contents)
                header = struct.pack(">BBIIBIH", FileTransferService.WRITE, FileTransferService.OK, i, total_files, flags, content_length, len(encoded_filename))
                packet = header + encoded_filename
                write_packets(packet)

            header = struct.pack(">BBIIBIH", FileTransferService.WRITE, FileTransferService.OK, total_files, total_files, 0, 0, 0)
            write_packets(header)
        elif command == adafruit_ble_file_transfer.FileTransferService.DELETE:
            path_length = struct.unpack_from(">H", p, offset=1)[0]
            path_start = struct.calcsize(">BH")
            path = read_complete_path(p[path_start:], path_length)
            d = find_dir(path)
            filename = path.split("/")[-1]
            if not filename and d:
                print("trying to delete directory with contents")
                error_response = struct.pack(">BB", FileTransferService.WRITE, FileTransferService.ERR)
                write_packets(error_response)
                continue

            # We're a directory.
            if not filename:
                path = path[:-1]
                filename = path.split("/")[-1]
                d = find_dir(path)

            if filename not in d:
                print("missing path")
                error_response = struct.pack(">BB", FileTransferService.WRITE, FileTransferService.ERR)
                write_packets(error_response)
                continue
            ok = True

            del d[filename]
            
            header = struct.pack(">BB", FileTransferService.WRITE, FileTransferService.OK)
            write_packets(header)
        else:
            print("unknown command", command)
    print("disconnected")


# SPDX-FileCopyrightText: Copyright (c) 2021 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: Unlicense

"""This example broadcasts out the creation id based on the CircuitPython machine
   string and provides a stub FileTransferService."""

import struct
import os

import adafruit_ble
import adafruit_ble_creation

import adafruit_ble_file_transfer
from adafruit_ble_file_transfer import FileTransferService

cid = adafruit_ble_creation.creation_ids[os.uname().machine]

ble = adafruit_ble.BLERadio()
# ble._adapter.erase_bonding()

service = FileTransferService()
print(ble.name)
advert = adafruit_ble_creation.Creation(creation_id=cid, services=[service])
print(bytes(advert), len(bytes(advert)))

CHUNK_SIZE = 4000

stored_data = {}


def find_dir(full_path):
    parts = full_path.split("/")
    parent_dir = stored_data
    k = 1
    while k < len(parts) - 1:
        part = parts[k]
        if part not in parent_dir:
            return None
        parent_dir = parent_dir[part]
        k += 1
    return parent_dir


def read_packets(buf, *, target_size=None):
    if not target_size:
        target_size = len(buf)
    total_read = 0
    buf = memoryview(buf)
    while total_read < target_size:
        count = service.raw.readinto(buf[total_read:])
        total_read += count

    return total_read


def write_packets(buf):
    packet_length = service.raw.outgoing_packet_length
    if len(buf) <= packet_length:
        service.raw.write(buf)
        return

    full_packet = memoryview(bytearray(packet_length))
    sent = 0
    while offset < len(buf):
        this_packet = full_packet[: len(buf) - sent]
        for k in range(len(this_packet)):  # pylint: disable=consider-using-enumerate
            this_packet[k] = buf[sent + k]
        sent += len(this_packet)
        service.raw.write(this_packet)


def read_complete_path(starting_path, total_length):
    complete_path = bytearray(total_length)
    current_path_length = len(starting_path)
    remaining_path = total_length - current_path_length
    complete_path[:current_path_length] = starting_path
    if remaining_path > 0:
        read_packets(
            memoryview(complete_path)[current_path_length:], target_size=remaining_path
        )
    return str(complete_path, "utf-8")


packet_buffer = bytearray(CHUNK_SIZE + 20)
while True:
    ble.start_advertising(advert)
    while not ble.connected:
        pass
    while ble.connected:
        try:
            read = service.raw.readinto(packet_buffer)
        except ConnectionError:
            continue
        if read == 0:
            continue

        p = packet_buffer[:read]
        command = struct.unpack_from("<B", p)[0]
        if command == FileTransferService.WRITE:
            start_offset, content_length, path_length = struct.unpack_from(
                "<IIH", p, offset=1
            )
            path_start = struct.calcsize("<BIIH")
            path = read_complete_path(p[path_start:], path_length)

            d = find_dir(path)
            filename = path.split("/")[-1]
            if filename not in d:
                contents = bytearray(content_length)
                d[filename] = contents
            current_len = len(d[filename])
            if current_len < content_length:
                contents = d[filename] + bytearray(content_length - current_len)
            elif current_len > content_length:
                contents = d[filename][:content_length]
            else:
                contents = d[filename]
            d[filename] = contents
            contents_read = start_offset
            write_data_header_size = struct.calcsize("<BBII")
            data_size = 0
            ok = True

            while contents_read < content_length and ok:
                next_amount = min(CHUNK_SIZE, content_length - contents_read)
                header = struct.pack(
                    "<BBII",
                    FileTransferService.WRITE_PACING,
                    FileTransferService.OK,
                    contents_read,
                    next_amount,
                )
                write_packets(header)
                read = read_packets(
                    packet_buffer, target_size=next_amount + write_data_header_size
                )
                cmd, status, offset, data_size = struct.unpack_from(
                    "<BBII", packet_buffer
                )
                if status != FileTransferService.OK:
                    print("bad status, resetting")
                    ok = False
                if cmd != FileTransferService.WRITE_DATA:
                    write_packets(
                        struct.pack(
                            "<BBII",
                            FileTransferService.WRITE_PACING,
                            FileTransferService.ERROR_PROTOCOL,
                            0,
                            0,
                        )
                    )
                    print("protocol error, resetting")
                    ok = False

                contents[contents_read : contents_read + data_size] = packet_buffer[
                    write_data_header_size : write_data_header_size + data_size
                ]
                contents_read += data_size
            if not ok:
                break

            write_packets(
                struct.pack(
                    "<BBII",
                    FileTransferService.WRITE_PACING,
                    FileTransferService.OK,
                    content_length,
                    0,
                )
            )
        elif command == adafruit_ble_file_transfer.FileTransferService.READ:
            offset, free_space, path_length = struct.unpack_from("<IIH", p, offset=1)
            path_start = struct.calcsize("<BIIH")
            path = read_complete_path(p[path_start:], path_length)
            d = find_dir(path)
            filename = path.split("/")[-1]
            if filename not in d:
                print("missing path")
                error_response = struct.pack(
                    "<BBIII",
                    FileTransferService.READ_DATA,
                    FileTransferService.ERR,
                    0,
                    0,
                    0,
                )
                write_packets(error_response)
                continue

            contents_sent = offset
            contents = d[filename]
            while contents_sent < len(contents):
                remaining = len(contents) - contents_sent
                next_amount = min(remaining, free_space)
                header = struct.pack(
                    "<BBIII",
                    FileTransferService.READ_DATA,
                    FileTransferService.OK,
                    contents_sent,
                    len(contents),
                    next_amount,
                )
                write_packets(
                    header + contents[contents_sent : contents_sent + next_amount]
                )
                contents_sent += next_amount

                if contents_sent == len(contents):
                    break

                read = read_packets(packet_buffer, target_size=struct.calcsize("<BBII"))
                cmd, status, offset, free_space = struct.unpack_from(
                    "<BBII", packet_buffer
                )
                if cmd != FileTransferService.READ_PACING:
                    write_packets(
                        struct.pack(
                            "<BBIII",
                            FileTransferService.READ_DATA,
                            FileTransferService.ERROR_PROTOCOL,
                            0,
                            0,
                            0,
                        )
                    )
                    print("protocol error", packet_buffer[:10])
                    break
                if offset != contents_sent:
                    write_packets(
                        struct.pack(
                            "<BBIII",
                            FileTransferService.READ_DATA,
                            FileTransferService.ERROR_PROTOCOL,
                            0,
                            0,
                            0,
                        )
                    )
                    print("mismatched offset")
                    break
        elif command == adafruit_ble_file_transfer.FileTransferService.MKDIR:
            path_length = struct.unpack_from("<H", p, offset=1)[0]
            path_start = struct.calcsize("<BH")
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
                header = struct.pack(
                    "<BB", FileTransferService.MKDIR_STATUS, FileTransferService.OK
                )
            else:
                header = struct.pack(
                    "<BB", FileTransferService.MKDIR_STATUS, FileTransferService.ERR
                )
            write_packets(header)
        elif command == adafruit_ble_file_transfer.FileTransferService.LISTDIR:
            path_length = struct.unpack_from("<H", p, offset=1)[0]
            path_start = struct.calcsize("<BH")
            path = read_complete_path(p[path_start:], path_length)

            # cmd, status, i, total, flags, file_size, path_length = struct.unpack("<BBIIBIH", b)

            d = find_dir(path)
            if d is None:
                error = struct.pack(
                    "<BBIIIIH",
                    FileTransferService.LISTDIR_ENTRY,
                    FileTransferService.ERROR,
                    0,
                    0,
                    0,
                    0,
                    0,
                )
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
                header = struct.pack(
                    "<BBIIIIH",
                    FileTransferService.LISTDIR_ENTRY,
                    FileTransferService.OK,
                    i,
                    total_files,
                    flags,
                    content_length,
                    len(encoded_filename),
                )
                packet = header + encoded_filename
                write_packets(packet)

            header = struct.pack(
                "<BBIIIIH",
                FileTransferService.LISTDIR_ENTRY,
                FileTransferService.OK,
                total_files,
                total_files,
                0,
                0,
                0,
            )
            write_packets(header)
        elif command == adafruit_ble_file_transfer.FileTransferService.DELETE:
            path_length = struct.unpack_from("<H", p, offset=1)[0]
            path_start = struct.calcsize("<BH")
            path = read_complete_path(p[path_start:], path_length)
            d = find_dir(path)
            filename = path.split("/")[-1]
            if not filename and d:
                print("trying to delete directory with contents")
                error_response = struct.pack(
                    "<BB", FileTransferService.DELETE_STATUS, FileTransferService.ERROR
                )
                write_packets(error_response)
                continue

            # We're a directory.
            if not filename:
                path = path[:-1]
                filename = path.split("/")[-1]
                d = find_dir(path)

            if filename not in d:
                print("missing path", path, d)
                error_response = struct.pack(
                    "<BB", FileTransferService.DELETE_STATUS, FileTransferService.ERROR
                )
                write_packets(error_response)
                continue
            ok = True

            del d[filename]

            header = struct.pack(
                "<BB", FileTransferService.DELETE_STATUS, FileTransferService.OK
            )
            write_packets(header)
        else:
            print("unknown command", hex(command))
    print("disconnected")

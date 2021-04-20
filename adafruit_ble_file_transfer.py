# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2021 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
`adafruit_ble_file_transfer`
================================================================================

Simple BLE Service for reading and writing files over BLE


* Author(s): Scott Shawcroft
"""

import struct
import _bleio

from adafruit_ble.attributes import Attribute
from adafruit_ble.characteristics import Characteristic, ComplexCharacteristic
from adafruit_ble.characteristics.int import Uint32Characteristic
from adafruit_ble.uuid import VendorUUID, StandardUUID
from adafruit_ble.services import Service

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_BLE_File_Transfer.git"

CHUNK_SIZE = 490


class FileTransferUUID(VendorUUID):
    """UUIDs with the CircuitPython base UUID."""

    # pylint: disable=too-few-public-methods

    def __init__(self, uuid16):
        uuid128 = bytearray("refsnarTeliF".encode("utf-8") + b"\x00\x00\xaf\xad")
        uuid128[-3] = uuid16 >> 8
        uuid128[-4] = uuid16 & 0xFF
        super().__init__(uuid128)


class _TransferCharacteristic(ComplexCharacteristic):
    """Endpoint for sending commands to a media player. The value read will list all available
    commands."""

    # pylint: disable=too-few-public-methods

    uuid = FileTransferUUID(0x0200)

    def __init__(self):
        super().__init__(
            properties=Characteristic.WRITE_NO_RESPONSE
            | Characteristic.READ
            | Characteristic.NOTIFY,
            read_perm=Attribute.ENCRYPT_NO_MITM,
            write_perm=Attribute.ENCRYPT_NO_MITM,
            max_length=512,
            fixed_length=False,
        )

    def bind(self, service):
        """Binds the characteristic to the given Service."""
        bound_characteristic = super().bind(service)
        return _bleio.PacketBuffer(
            bound_characteristic, buffer_size=4, max_packet_size=512
        )


class FileTransferService(Service):
    """Simple (not necessarily fast) BLE file transfer service. It implements basic CRUD operations.

    The server dictates data transfer chunk sizes so it can minimize buffer sizes on its end.
    """

    # pylint: disable=too-few-public-methods

    uuid = StandardUUID(0xFEBB)
    version = Uint32Characteristic(uuid=FileTransferUUID(0x0100))
    raw = _TransferCharacteristic()
    # _raw gets shadowed for each MIDIService instance by a PacketBuffer. PyLint doesn't know this
    # so it complains about missing members.
    # pylint: disable=no-member

    # Commands
    INVALID = 0x00
    READ = 0x10
    READ_DATA = 0x11
    READ_PACING = 0x12
    WRITE = 0x20
    WRITE_PACING = 0x21
    WRITE_DATA = 0x22
    DELETE = 0x30
    DELETE_STATUS = 0x31
    MKDIR = 0x40
    MKDIR_STATUS = 0x41
    LISTDIR = 0x50
    LISTDIR_ENTRY = 0x51

    # Responses
    # 0x00 is INVALID
    OK = 0x01  # pylint: disable=invalid-name
    ERROR = 0x02
    ERROR_NO_FILE = 0x03
    ERROR_PROTOCOL = 0x04

    # Flags
    DIRECTORY = 0x01


class ProtocolError(BaseException):
    """Error thrown when expected bytes don't match"""


class FileTransferClient:
    """Helper class to communicating with a File Transfer server"""

    def __init__(self, service):
        self._service = service

    def _write(self, buffer):
        sent = 0
        while sent < len(buffer):
            remaining = len(buffer) - sent
            next_send = min(self._service.raw.outgoing_packet_length, remaining)
            self._service.raw.write(buffer[sent : sent + next_send])
            sent += next_send

    def _readinto(self, buffer):
        read = 0
        # Read back how much we can write
        while read == 0:
            try:
                read = self._service.raw.readinto(buffer)
            except ValueError as error:
                print(error)
                long_buffer = bytearray(512)
                read = self._service.raw.readinto(long_buffer)
                print("long packet", long_buffer[:read])
        return read

    def read(self, path, *, offset=0):
        """Returns the contents of the file at the given path starting at the given offset"""
        path = path.encode("utf-8")
        chunk_size = CHUNK_SIZE
        encoded = (
            struct.pack(
                "<BxHII", FileTransferService.READ, len(path), offset, chunk_size
            )
            + path
        )
        self._write(encoded)
        b = bytearray(struct.calcsize("<BBxxIII") + chunk_size)
        current_offset = offset
        content_length = None
        buf = None
        data_header_size = struct.calcsize("<BBxxIII")
        while content_length is None or current_offset < content_length:
            read = self._readinto(b)
            (
                cmd,
                status,
                current_offset,
                content_length,
                _,
            ) = struct.unpack_from("<BBxxIII", b)
            if cmd != FileTransferService.READ_DATA:
                raise ProtocolError("Incorrect reply")
            if status != FileTransferService.OK:
                raise ValueError("Missing file")
            if buf is None:
                buf = bytearray(content_length - offset)
            out_offset = current_offset - offset
            buf[out_offset : out_offset + (read - data_header_size)] = b[
                data_header_size:read
            ]
            current_offset += read - data_header_size
            chunk_size = min(CHUNK_SIZE, content_length - current_offset)
            if chunk_size == 0:
                break
            encoded = struct.pack(
                "<BBxxII",
                FileTransferService.READ_PACING,
                FileTransferService.OK,
                current_offset,
                chunk_size,
            )
            self._write(encoded)
        return buf

    def write(self, path, contents, *, offset=0):
        """Writes the given contents to the given path starting at the given offset.

        If the file is shorter than the offset, zeros will be added in the gap."""
        path = path.encode("utf-8")
        total_length = len(contents) + offset
        encoded = (
            struct.pack(
                "<BxHII", FileTransferService.WRITE, len(path), offset, total_length
            )
            + path
        )
        self._write(encoded)
        b = bytearray(struct.calcsize("<BBxxII"))
        written = 0
        while written < len(contents):
            self._readinto(b)
            cmd, status, current_offset, free_space = struct.unpack("<BBxxII", b)
            if status != FileTransferService.OK:
                raise RuntimeError()
            if (
                cmd != FileTransferService.WRITE_PACING
                or current_offset != written + offset
            ):
                self._write(
                    struct.pack(
                        "<BBxxII",
                        FileTransferService.WRITE_DATA,
                        FileTransferService.ERROR_PROTOCOL,
                        0,
                        0,
                    )
                )
                raise ProtocolError()

            self._write(
                struct.pack(
                    "<BBxxII",
                    FileTransferService.WRITE_DATA,
                    FileTransferService.OK,
                    current_offset,
                    free_space,
                )
            )
            self._write(contents[written : written + free_space])
            written += free_space

        # Wait for confirmation that everything was written ok.
        self._readinto(b)
        cmd, status, offset, free_space = struct.unpack("<BBxxII", b)
        if cmd != FileTransferService.WRITE_PACING or offset != total_length:
            raise ProtocolError()

    def mkdir(self, path):
        """Makes the directory and any missing parents"""
        path = path.encode("utf-8")
        encoded = struct.pack("<BxH", FileTransferService.MKDIR, len(path)) + path
        self._write(encoded)

        b = bytearray(struct.calcsize("<BB"))
        self._readinto(b)
        cmd, status = struct.unpack("<BB", b)
        if cmd != FileTransferService.MKDIR_STATUS:
            raise ProtocolError()
        if status != FileTransferService.OK:
            raise ValueError("Invalid path")

    def listdir(self, path):
        """Returns a list of tuples, one tuple for each file or directory in the given path"""
        paths = []
        path = path.encode("utf-8")
        encoded = struct.pack("<BxH", FileTransferService.LISTDIR, len(path)) + path
        self._write(encoded)
        b = bytearray(self._service.raw.incoming_packet_length)
        i = 0
        total = 10  # starting value that will be replaced by the first response
        header_size = struct.calcsize("<BBHIIII")
        while i < total:
            read = self._readinto(b)
            offset = 0
            while offset < read:
                (
                    cmd,
                    status,
                    path_length,
                    i,
                    total,
                    flags,
                    file_size,
                ) = struct.unpack_from("<BBHIIII", b, offset=offset)
                if cmd != FileTransferService.LISTDIR_ENTRY:
                    raise ProtocolError()
                if i >= total:
                    break
                path = str(
                    b[offset + header_size : offset + header_size + path_length],
                    "utf-8",
                )
                paths.append((path, file_size, flags))
                offset += header_size + path_length
                if status != FileTransferService.OK:
                    break
        return paths

    def delete(self, path):
        """Deletes the file or directory at the given path. Directories must be empty."""
        path = path.encode("utf-8")
        encoded = struct.pack("<BxH", FileTransferService.DELETE, len(path)) + path
        self._write(encoded)

        b = bytearray(struct.calcsize("<BB"))
        self._readinto(b)
        cmd, status = struct.unpack("<BB", b)
        if cmd != FileTransferService.DELETE_STATUS:
            raise ProtocolError()
        if status != FileTransferService.OK:
            raise ValueError("Missing file")

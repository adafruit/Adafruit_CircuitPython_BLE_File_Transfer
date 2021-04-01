# SPDX-FileCopyrightText: 2017 Scott Shawcroft, written for Adafruit Industries
# SPDX-FileCopyrightText: Copyright (c) 2021 Scott Shawcroft for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
`adafruit_ble_file_transfer`
================================================================================

Simple BLE Service for reading and writing files over BLE


* Author(s): Scott Shawcroft

Implementation Notes
--------------------

**Hardware:**

.. todo:: Add links to any specific hardware product page(s), or category page(s).
  Use unordered list & hyperlink rST inline format: "* `Link Text <url>`_"

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases

.. todo:: Uncomment or remove the Bus Device and/or the Register library dependencies
  based on the library's use of either.

# * Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice
# * Adafruit's Register library: https://github.com/adafruit/Adafruit_CircuitPython_Register
"""

import _bleio
import struct

from adafruit_ble.attributes import Attribute
from adafruit_ble.characteristics import Characteristic, ComplexCharacteristic
from adafruit_ble.characteristics.int import Uint32Characteristic
from adafruit_ble.uuid import VendorUUID, StandardUUID
from adafruit_ble.services import Service

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_BLE_File_Transfer.git"


class FileTransferUUID(VendorUUID):
    """UUIDs with the CircuitPython base UUID."""

    def __init__(self, uuid16):
        uuid128 = bytearray("!refsnaTeliF".encode("utf-8") + b"\x00\x00\xaf\xad")
        uuid128[-3] = uuid16 >> 8
        uuid128[-4] = uuid16 & 0xFF
        super().__init__(uuid128)

class _TransferCharacteristic(ComplexCharacteristic):
    """Endpoint for sending commands to a media player. The value read will list all available
    commands."""

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
        return _bleio.PacketBuffer(bound_characteristic, buffer_size=4)

class FileTransferService(Service):
    """Simple (not necessarily fast) BLE file transfer service. It implements basic CRUD operations.

    The server dictates data transfer chunk sizes so it can minimize buffer sizes on its end.
    """

    uuid = StandardUUID(0xfebb)
    version = Uint32Characteristic(uuid=FileTransferUUID(0x0100))
    raw = _TransferCharacteristic()
    # _raw gets shadowed for each MIDIService instance by a PacketBuffer. PyLint doesn't know this
    # so it complains about missing members.
    # pylint: disable=no-member

    # Actions
    INVALID = 0x00
    READ = 0x01
    WRITE = 0x02
    DELETE = 0x03
    LIST = 0x04

    # Responses
    # 0x00 is INVALID
    OK = 0x81
    ERR = 0x82

class FileTransferClient:
    def __init__(self, service):
        self._service = service

    def read(self, path):
        print("read", path)
        path = path.encode("utf-8")
        chunk_size = 10
        encoded = struct.pack(">BIH", FileTransferService.READ, chunk_size, len(path)) + path
        # TODO: we may need to split this packet up.
        r = self._service.raw.write(encoded)
        b = bytearray(struct.calcsize(">BBI"))
        print("write", r, encoded)
        contents_read = 0
        content_length = None
        buf = None
        while content_length is None or contents_read < content_length:
            read = 0
            # Read back how much we can write
            while read == 0:
                read = self._service.raw.readinto(b)
            cmd, status, content_length = struct.unpack_from(">BBI", b)
            if buf is None:
                buf = bytearray(content_length)
            header_size = struct.calcsize(">BBI")
            buf[contents_read:contents_read + (read - header_size)] = b[header_size:]
            contents_read += read - header_size
        return buf
    
    def write(self, path, contents):
        print("write", path, contents)
        path = path.encode("utf-8")
        encoded = struct.pack(">BIH", FileTransferService.WRITE, len(contents), len(path)) + path
        # TODO: we may need to split this packet up.
        r = self._service.raw.write(encoded)
        b = bytearray(struct.calcsize(">BBI"))
        print("write", r, encoded)
        written = 0
        while written < len(contents):
            read = 0
            # Read back how much we can write
            while read == 0:
                read = self._service.raw.readinto(b)
            cmd, status, free_space = struct.unpack(">BBI", b)
            print(cmd, status, free_space)
            self._service.raw.write(contents[written:written+free_space])
            written += free_space

    def delete(self, path):
        print("delete", path)

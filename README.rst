Introduction
============


.. image:: https://readthedocs.org/projects/adafruit-circuitpython-ble_file_transfer/badge/?version=latest
    :target: https://circuitpython.readthedocs.io/projects/ble_file_transfer/en/latest/
    :alt: Documentation Status


.. image:: https://img.shields.io/discord/327254708534116352.svg
    :target: https://adafru.it/discord
    :alt: Discord


.. image:: https://github.com/adafruit/Adafruit_CircuitPython_BLE_File_Transfer/workflows/Build%20CI/badge.svg
    :target: https://github.com/adafruit/Adafruit_CircuitPython_BLE_File_Transfer/actions
    :alt: Build Status


.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Code Style: Black

Simple BLE Service for reading and writing files over BLE. This BLE service is geared towards file
transfer to and from a device running the service. A core part of the protocol is free space
responses so that the server can be a memory limited device. The free space responses allow for
small buffer sizes that won't be overwhelmed by the client.


Dependencies
=============
This driver depends on:

* `Adafruit CircuitPython <https://github.com/adafruit/circuitpython>`_

Please ensure all dependencies are available on the CircuitPython filesystem.
This is easily achieved by downloading
`the Adafruit library and driver bundle <https://circuitpython.org/libraries>`_
or individual libraries can be installed using
`circup <https://github.com/adafruit/circup>`_.


Installing from PyPI
=====================

On supported GNU/Linux systems like the Raspberry Pi, you can install the driver locally `from
PyPI <https://pypi.org/project/adafruit-circuitpython-ble_file_transfer/>`_.
To install for current user:

.. code-block:: shell

    pip3 install adafruit-circuitpython-ble-file-transfer

To install system-wide (this may be required in some cases):

.. code-block:: shell

    sudo pip3 install adafruit-circuitpython-ble-file-transfer

To install in a virtual environment in your current project:

.. code-block:: shell

    mkdir project-name && cd project-name
    python3 -m venv .env
    source .env/bin/activate
    pip3 install adafruit-circuitpython-ble-file-transfer



Usage Examples
==============

See `examples/ble_file_transfer_simpletest.py <examples/ble_file_transfer_simpletest.py>`_ for a client example. A stub server implementation is in `examples/ble_file_transfer_stub_server.py <examples/ble_file_transfer_stub_server.py>`_.

Protocol
=========

The file transfer protocol is meant to be simple and easy to implement. It uses free space counts as a way to rate limit file content data transfer. All multi-byte numbers are encoded with the least significant byte first ("<" in CPython's struct module).

GATT Service
--------------

The UUID of the service is ``0xfebb``, Adafruit's 16-bit service UUID.

The base UUID used in characteristics is ``ADAFxxxx-4669-6C65-5472-616E73666572``. The 16-bit numbers below are substituted into the ``xxxx`` portion.

The service has two characteristics:

* version (``0x0100``) - Simple unsigned 32-bit integer version number. Always 1.
* raw transfer (``0x0200``) - Bidirectional link with a custom protocol. The client does WRITE_NO_RESPONSE to the characteristic and then server replies via NOTIFY. (This is similar to the Nordic UART Service but on a single characteristic rather than two.) The commands over the transfer characteristic are idempotent and stateless. A disconnect during a command will reset the state.

Commands
---------

Commands always start with a fixed header. The first entry is always the command number itself encoded in a single byte. The number of subsequent entries in the header will vary by command. The entire header must be sent as a unit so set the characteristic with the full header packet. You can combine multiple commands into a single write as long as the complete header is in the packet.

Paths use ``/`` as a separator and full paths must start with ``/``. Directory paths
must end with ``/`` when provided as a full path.

All numbers are unsigned.

All values are aligned with respect to the start of the packet.

Status bytes are ``0x01`` for OK and ``0x02`` for error. Other values for error may be used for specific commands.

``0x10`` - Read a file
++++++++++++++++++++++

Given a full path, returns the full contents of the file.

The header is four fixed entries and a variable length path:

* Command: Single byte. Always ``0x10``.
* 1 Byte reserved for padding.
* Path length: 16-bit number encoding the encoded length of the path string.
* Chunk offset: 32-bit number encoding the offset into the file to start the first chunk.
* Chunk size: 32-bit number encoding the amount of data that the client can handle in the first reply.
* Path: UTF-8 encoded string that is *not* null terminated. (We send the length instead.)

The server will respond with:

* Command: Single byte. Always ``0x11``.
* Status: Single byte.
* 2 Bytes reserved for padding.
* Chunk offset: 32-bit number encoding the offset into the file of this chunk.
* Total length: 32-bit number encoding the total file length.
* Chunk length: 32-bit number encoding the length of the read data up to the chunk size provided in the header.
* Chunk-length contents of the file starting from the current position.

If the chunk length is smaller than the total length, then the client will request more data by sending:

* Command: Single byte. Always ``0x12``.
* Status: Single byte. Always OK for now.
* 2 Bytes reserved for padding.
* Chunk offset: 32-bit number encoding the offset into the file to start the next chunk.
* Chunk size: 32-bit number encoding the number of bytes to read. May be different than the original size. Does not need to be limited by the total size.

The transaction is complete after the server has replied with all data. (No acknowledgement needed from the client.)

``0x20`` - Write a file
+++++++++++++++++++++++

Writes the content to the given full path. If the file exists, it will be overwritten. Content may be written as received so an interrupted transfer may lead to a truncated file.

Offset larger than the existing file size will introduce zeros into the gap.

The header is four fixed entries and a variable length path:

* Command: Single byte. Always ``0x20``.
* 1 Byte reserved for padding.
* Path length: 16-bit number encoding the encoded length of the path string.
* Offset: 32-bit number encoding the starting offset to write.
* Total size: 32-bit number encoding the total length of the file contents.
* Path: UTF-8 encoded string that is *not* null terminated. (We send the length instead.)

The server will repeatedly respond until the total length has been transferred with:

* Command: Single byte. Always ``0x21``.
* Status: Single byte. ``0x01`` if OK. ``0x02`` if any parent directory is missing or a file.
* 2 Bytes reserved for padding.
* Offset: 32-bit number encoding the starting offset to write. (Should match the offset from the previous 0x20 or 0x22 message)
* Free space: 32-bit number encoding the amount of data the client can send.

The client will repeatedly respond until the total length has been transferred with:

* Command: Single byte. Always ``0x22``.
* Status: Single byte. Always ``0x01`` for OK.
* 2 Bytes reserved for padding.
* Offset: 32-bit number encoding the offset to write.
* Data size: 32-bit number encoding the amount of data the client is sending.
* Data

The transaction is complete after the server has received all data and replied with a status with 0 free space and offset set to the content length.


``0x30`` - Delete a file or directory
+++++++++++++++++++++++++++++++++++++

Deletes the file or directory at the given full path. Directories must be empty to be deleted.

The header is two fixed entries and a variable length path:

* Command: Single byte. Always ``0x30``.
* 1 Byte reserved for padding.
* Path length: 16-bit number encoding the encoded length of the path string.
* Path: UTF-8 encoded string that is *not* null terminated. (We send the length instead.)

The server will reply with:

* Command: Single byte. Always ``0x31``.
* Status: Single byte. ``0x01`` if the file or directory was deleted or ``0x02`` if the path is a non-empty directory or non-existent.

``0x40`` - Make a directory
+++++++++++++++++++++++++++

Creates a new directory at the given full path. If a parent directory does not exist, then it will also be created. If any name conflicts with an existing file, an error will be returned.

The header is two fixed entries and a variable length path:

* Command: Single byte. Always ``0x40``.
* 1 Byte reserved for padding.
* Path length: 16-bit number encoding the encoded length of the path string.
* Path: UTF-8 encoded string that is *not* null terminated. (We send the length instead.)

The server will reply with:

* Command: Single byte. Always ``0x41``.
* Status: Single byte. ``0x01`` if the directory(s) were created or ``0x02`` if any parent of the path is an existing file.

``0x50`` - List a directory
+++++++++++++++++++++++++++

Lists all of the contents in a directory given a full path. Returned paths are *relative* to the given path to reduce duplication.

The header is two fixed entries and a variable length path:

* Command: Single byte. Always ``0x50``.
* 1 Byte reserved for padding.
* Path length: 16-bit number encoding the encoded length of the path string.
* Path: UTF-8 encoded string that is *not* null terminated. (We send the length instead.)

The server will reply with n+1 entries for a directory with n files:

* Command: Single byte. Always ``0x51``.
* Status: Single byte. ``0x01`` if the directory exists or ``0x02`` if it doesn't.
* Path length: 16-bit number encoding the encoded length of the path string.
* Entry number: 32-bit number encoding the entry number.
* Total entries: 32-bit number encoding the total number of entries.
* Flags: 32-bit number encoding data about the entries.

  - Bit 0: Set when the entry is a directory
  - Bits 1-7: Reserved

* File size: 32-bit number encoding the size of the file. Ignore for directories. Value may change.
* Path: UTF-8 encoded string that is *not* null terminated. (We send the length instead.) These paths are relative so they won't contain ``/`` at all.

The transaction is complete when the final entry is sent from the server. It will have entry number == total entries and zeros for flags, file size and path length.

Contributing
============

Contributions are welcome! Please read our `Code of Conduct
<https://github.com/adafruit/Adafruit_CircuitPython_BLE_File_Transfer/blob/main/CODE_OF_CONDUCT.md>`_
before contributing to help this project stay welcoming.

Documentation
=============

For information on building library documentation, please check out
`this guide <https://learn.adafruit.com/creating-and-sharing-a-circuitpython-library/sharing-our-docs-on-readthedocs#sphinx-5-1>`_.

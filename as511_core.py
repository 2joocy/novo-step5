# as511_core.py

import serial
import time
import struct
import difflib

# AS511 control codes
STX = 0x02
DLE = 0x10
ETX = 0x03
ACK = 0x06
NAK = 0x15

# Function codes
B_INFO     = 0x1A  # block info
DB_READ    = 0x04  # read block
DB_WRITE   = 0x05  # write block (optional)
# … other codes as needed

# -----------------------------------------------------------------------------
# Block-type map: type ID → block_ids (used by compare_gui)
# -----------------------------------------------------------------------------
TYPE_MAP = {
    1:    'DB',   # Data Block
    2:    'SB',   # System Block
    4:    'PB',   # Peripheral Block
    8:    'FB',   # Function Block
    0x30: 'OB',   # Organization Block
    0x4C: 'FX',   # Special Function Block
    0x90: 'DX',   # Extended Data Block
}

# at bottom of as511_core.py
# Existing: TYPE_MAP = {1:'DB', 2:'SB', 4:'PB', 8:'FB', …}

# Reverse lookup: name → type ID
NAME_TO_ID = {name: tid for tid, name in TYPE_MAP.items()}

# Maximum data per telegram (bytes)
MAX_TELEGRAM = 512


class ExtendedAS511Client:
    """
    Context-managed client for Siemens S5 AS511 protocol.
    Handles handshake, DLE stuffing/unstuffing, multi-part reads,
    block listing, read/write, and binary diffs.
    """

    def __init__(self, device, baudrate=9600, plc_address=2,
                 timeout=1.0, retries=3):
        self.device = device
        self.baudrate = baudrate
        self.plc_address = plc_address
        self.timeout = timeout
        self.retries = retries
        self._ser = None

    def __enter__(self):
        self._ser.rts = True
        self._ser.dtr = True
        self._ser = serial.Serial(
            port=self.device,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.timeout
        )
        self._handshake()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._ser and self._ser.is_open:
            self._ser.close()

    def close(self):
        """Alias for __exit__"""
        if self._ser:
            self._ser.close()

    def _handshake(self):
        """STX → expect DLE,ACK (or NAK)"""
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()
        self._ser.write(bytes([STX]))
        resp = self._ser.read(2)
        if resp == bytes([DLE, ACK]):
            return
        elif resp == bytes([DLE, NAK]):
            raise RuntimeError("PLC NAK on handshake")
        else:
            raise RuntimeError(f"Unexpected handshake reply: {resp!r}")

    @staticmethod
    def _dle_stuff(data: bytes) -> bytes:
        """Duplicate any DLE bytes in payload."""
        return data.replace(bytes([DLE]), bytes([DLE, DLE]))

    @staticmethod
    def _dle_unstuff(data: bytes) -> bytes:
        """Collapse DLE DLE sequences into one data byte."""
        return data.replace(bytes([DLE, DLE]), bytes([DLE]))

    def _send_frame(self, func: int, payload: bytes = b"") -> bytes:
        """
        Build and send a framed AS511 telegram:
          DLE STX, FUNC, (PAYLOAD with DLE-stuffing), DLE ETX
        Then read back until DLE ETX, unstuff and return the raw payload.
        """
        # frame: DLE STX FUNCTION [plc_address?] PAYLOAD DLE ETX
        # Note: some variants require including plc_address byte here.
        header = bytes([DLE, STX, func])
        stuffed = self._dle_stuff(payload)
        frame = header + stuffed + bytes([DLE, ETX])
        self._ser.reset_input_buffer()
        self._ser.write(frame)

        # read-and-collect
        buf = bytearray()
        start = time.time()
        while True:
            chunk = self._ser.read(1)
            if not chunk:
                # timeout
                break
            buf += chunk
            if buf[-2:] == bytes([DLE, ETX]):
                # reached end-of-frame
                break
            # prevent infinite loop
            if time.time() - start > self.timeout + 0.5:
                break

        # remove trailing DLE ETX if present
        if buf[-2:] == bytes([DLE, ETX]):
            buf = buf[:-2]

        # unstuff
        return self._dle_unstuff(bytes(buf))

    def info_block(self, block_number: int):
        """
        Query block info (type, number, length_in_words).
        Returns (type_id, block_number, length_in_words).
        """
        # payload: block number (1 byte), PLC address
        payload = struct.pack(">B", block_number)
        data = self._send_frame(B_INFO, payload)
        # parse response:
        # assume data[0] = type_id, data[1] = block_number, data[2] = length_in_words
        if len(data) < 3:
            raise RuntimeError("B_INFO response too short")
        type_id, bn, lw = struct.unpack(">BBB", data[:3])
        return type_id, bn, lw

    def read_block(self, type_id: int, block_number: int, length_bytes: int):
        """
        Read the raw bytes of a block.
        length_bytes = length_in_words * 2
        Returns bytes of that length.
        """
        # payload: block number, start offset (2 bytes), length (2 bytes)
        # Here we read entire block from 0 to length_bytes
        payload = struct.pack(">BHH", block_number, 0, length_bytes)
        data = bytearray()
        remaining = length_bytes
        while remaining > 0:
            chunk_size = min(remaining, MAX_TELEGRAM)
            # pack length for this chunk
            chunk_payload = struct.pack(">BHH", block_number, length_bytes-remaining, chunk_size)
            part = self._send_frame(DB_READ, chunk_payload)
            data += part
            remaining -= len(part)
        if len(data) != length_bytes:
            raise RuntimeError(f"Expected {length_bytes} bytes, got {len(data)}")
        return bytes(data)

    def write_block(self, type_id: int, block_number: int, data_bytes: bytes):
        """
        Write a block’s raw data back to the PLC.
        Splits into MAX_TELEGRAM-sized chunks if necessary.
        """
        total = len(data_bytes)
        offset = 0
        while offset < total:
            chunk = data_bytes[offset:offset+MAX_TELEGRAM]
            size = len(chunk)
            payload = struct.pack(">BHH", block_number, offset, size) + chunk
            self._send_frame(DB_WRITE, payload)
            offset += size

    def list_blocks(self, type_id: int):
        """
        Scan block numbers 1–255, yield those whose info_block reports matching type_id.
        """
        for bn in range(1, 256):
            try:
                t, _, _ = self.info_block(bn)
                if t == type_id:
                    yield bn
            except Exception:
                continue

    def compare_block(self, type_id: int, block_number: int, baseline_path: str):
        """
        Yield unified-diff lines between the local baseline file and
        the PLC’s block data (hex-dump).
        """
        remote = self.read_block(type_id, block_number,
                                 self.info_block(block_number)[2] * 2)
        local = open(baseline_path, "rb").read()
        # produce hex strings
        a = [f"{b:02X}" for b in local]
        b = [f"{b:02X}" for b in remote]
        diff = difflib.unified_diff(
            a, b,
            fromfile="baseline", tofile="online",
            lineterm=""
        )
        return diff

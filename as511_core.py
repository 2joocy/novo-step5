# as511_core.py
"""
as511_core.py

Robust, context-managed AS511 protocol client for Siemens S5,
plus a global TYPE_MAP for block-type lookups.
"""

# SPDX-License-Identifier: MIT
# Copyright © 2025 Novo Nordisk A/S

import time, logging, os, glob, difflib
from typing import Optional, Tuple, Iterable, Protocol

# If you’re using real serial ports:
try:
    import serial
    from serial.serialutil import SerialException
except ImportError:
    serial = None  # type: ignore

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


# -----------------------------------------------------------------------------
# Transport Protocol for Simulation or Real Serial
# -----------------------------------------------------------------------------
class SimulationTransport(Protocol):
    def write(self, data: bytes) -> int: ...
    def read(self, size: int = 1) -> bytes: ...
    def read_until(self, expected: bytes) -> bytes: ...
    def flush_input(self) -> None: ...
    def flush_output(self) -> None: ...
    def close(self) -> None: ...

# -----------------------------------------------------------------------------
# AS511 Error Classes
# -----------------------------------------------------------------------------
class AS511Error(Exception): ...
class LRCError(AS511Error): ...
class NAKError(AS511Error): ...
class TimeoutError(AS511Error): ...
class SerialInitError(AS511Error): ...

# -----------------------------------------------------------------------------
# Core AS511 Client - https://www.runmode.com/as511protocol_description.pdf
# -----------------------------------------------------------------------------
class AS511Client:
    STX = 0x02; 
    ETX = 0x03; 
    DLE = 0x10
    ACK = 0x06; 
    NAK = 0x15
    CMD_READ  = 0x10
    CMD_WRITE = 0x11
    CMD_INFO  = 0x1A

    def __init__(
        self,
        device: Optional[str] = None,
        baudrate: int = 9600,
        plc_address: int = 2,
        timeout: float = 0.5,
        retries: int = 3,
        logger: Optional[logging.Logger] = None,
        transport: Optional[SimulationTransport] = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.plc_address = plc_address
        self.timeout     = timeout
        self.retries     = retries

        if transport:
            self._ser = transport
        else:
            if serial is None:
                raise SerialInitError("pyserial not installed")
            try:
                self._ser = serial.Serial(
                    port=device,
                    baudrate=baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_EVEN,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=timeout
                )
            except SerialException as e:
                raise SerialInitError(f"Cannot open port {device}: {e}")

    def __enter__(self) -> "AS511Client":
        if hasattr(self._ser, "open") and not self._ser.is_open:
            self._ser.open()  # type: ignore
        self.logger.info("AS511 transport opened")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        try:    self._ser.close()
        except: pass
        self.logger.info("AS511 transport closed")

    def _calc_lrc(self, data: bytes) -> int:
        lrc = 0
        for b in data: lrc ^= b
        return lrc

    def _build_frame(self, payload: bytes) -> bytes:
        length = 1 + len(payload) + 1
        body   = bytes([length, self.plc_address]) + payload + bytes([self.ETX])
        return bytes([self.STX]) + body + bytes([self._calc_lrc(body)])

    def _send_and_receive(self, frame: bytes) -> bytes:
        for attempt in range(1, self.retries + 1):
            self.logger.debug(f"→ {frame.hex()} (try {attempt})")
            self._ser.flush_input(); self._ser.flush_output()
            self._ser.write(frame)
            time.sleep(0.01)

            raw = self._ser.read_until(bytes([self.STX]))
            if not raw:
                self.logger.warning("Timeout waiting for STX, retry")
                continue
            hdr = self._ser.read(1)
            length = hdr[0]
            rest = self._ser.read(length + 1)
            reply = raw + hdr + rest

            if bytes([self.DLE, self.NAK]) in reply:
                raise NAKError("PLC responded with NAK")

            self.logger.debug(f"← {reply.hex()}")
            return reply

        raise TimeoutError("No valid reply after retries")

    def _parse_reply(self, raw: bytes) -> bytes:
        if raw[0] != self.STX:
            raise AS511Error("Invalid STX")
        length = raw[1]
        body = raw[2:2+length]
        if body[-1] != self.ETX:
            raise AS511Error("Missing ETX in body")
        lrc_rcvd = raw[2+length]
        if self._calc_lrc(raw[1:2+length+1]) != lrc_rcvd:
            raise LRCError("LRC mismatch")
        return body[1:-1]  # strip address + ETX

    def info_block(self, block_number: int) -> Tuple[int,int,int]:
        """Return (type_id, block_number, length_in_words)."""
        raw = self._send_and_receive(self._build_frame(bytes([self.CMD_INFO, block_number])))
        data = self._parse_reply(raw)
        return data[0], data[1], (data[-3]<<8) | data[-2]

    def read_block(self, block_type: int, block_number: int, byte_count: int) -> bytes:
        hi, lo = divmod(byte_count, 0x100)
        cmd = bytes([self.CMD_READ, block_type, block_number, hi, lo])
        raw = self._send_and_receive(self._build_frame(cmd))
        return self._parse_reply(raw)

    def write_block(self, block_type: int, block_number: int, data: bytes) -> None:
        hi, lo = divmod(len(data), 0x100)
        cmd = bytes([self.CMD_WRITE, block_type, block_number, hi, lo]) + data
        self._send_and_receive(self._build_frame(cmd))


class ExtendedAS511Client(AS511Client):
    """High-level helpers: list, download, upload, compare."""

    def list_blocks(self, type_id: int, max_blocks: int = 256) -> Iterable[int]:
        found = []
        for bn in range(max_blocks):
            try:
                t, _, _ = self.info_block(bn)
                if t == type_id:
                    found.append(bn)
            except AS511Error:
                continue
        return found

    def download_blocks(self, type_id: int, out_dir: str) -> Iterable[int]:
        os.makedirs(out_dir, exist_ok=True)
        blks = list(self.list_blocks(type_id))
        for i, bn in enumerate(blks, 1):
            _, _, lw = self.info_block(bn)
            data     = self.read_block(type_id, bn, lw*2)
            path     = os.path.join(out_dir, f"block_{type_id:02X}_{bn}.bin")
            with open(path, "wb") as f: f.write(data)
            self.logger.info(f"Saved block {bn} → {path}")
        return blks

    def upload_blocks(self, type_id: int, in_dir: str) -> Iterable[int]:
        files = glob.glob(f"{in_dir}/block_{type_id:02X}_*.bin")
        written = []
        for fn in files:
            bn = int(os.path.basename(fn).split('_')[-1].split('.')[0], 0)
            data = open(fn, "rb").read()
            self.write_block(type_id, bn, data)
            written.append(bn)
        return written

    def compare_block(self, type_id: int, block_number: int, file_path: str) -> Iterable[str]:
        local  = open(file_path, "rb").read()
        _, _, lw = self.info_block(block_number)
        remote = self.read_block(type_id, block_number, lw*2)

        def hexdump(buf: bytes):
            s = buf.hex()
            return [s[i:i+32] for i in range(0, len(s), 32)]

        return difflib.unified_diff(
            hexdump(remote), hexdump(local),
            fromfile=f"PLC_{block_number}", tofile=file_path, lineterm=""
        )

"""
as511_core.py

Contains core AS511 client and TYPE_MAP for use by any UI or CLI.
"""

import time
import difflib
import serial
import os
import logging

# Map from info_block() typeId → human-readable name
TYPE_MAP = {
    1:    'DB',   # Data Block
    2:    'SB',   # System Block
    4:    'PB',   # Peripheral Block
    8:    'FB',   # Function Block
    0x30: 'OB',   # Organization Block
    0x4C: 'FX',   # Special Function Block
    0x90: 'DX',   # Data eXtended
}

class AS511Client:
    STX       = 0x02
    ETX       = 0x03
    CMD_READ  = 0x10
    CMD_WRITE = 0x11
    CMD_INFO  = 0x1A  # B_INFO directory

    def __init__(self, device, baudrate=9600, plc_address=2,
                 timeout=1.0, retries=3, logger=None):
        self.ser         = serial.Serial(device, baudrate=baudrate, timeout=timeout)
        self.plc_address = plc_address
        self.timeout     = timeout
        self.retries     = retries
        self.log         = logger or logging.getLogger(__name__)

    def open(self):
        if not self.ser.is_open:
            self.ser.open()
        self.log.info(f"Opened {self.ser.port} @ {self.ser.baudrate}bps")

    def close(self):
        if self.ser.is_open:
            self.ser.close()
        self.log.info("Serial port closed")

    def _lrc(self, data: bytes) -> int:
        lrc = 0
        for b in data:
            lrc ^= b
        return lrc

    def _build_frame(self, cmd: bytes) -> bytes:
        length = 1 + len(cmd) + 1
        body   = bytes([length, self.plc_address]) + cmd + bytes([self.ETX])
        return bytes([self.STX]) + body + bytes([self._lrc(body)])

    def _send_frame(self, frame: bytes) -> bytes:
        for attempt in range(1, self.retries + 1):
            self.log.debug(f"→ {frame.hex()} (attempt {attempt})")
            self.ser.reset_input_buffer()
            self.ser.write(frame)
            time.sleep(0.05)
            reply = self.ser.read_until(expected=bytes([self.ETX]))
            if not reply:
                self.log.warning("No reply, retrying…")
                continue
            lrc = self.ser.read(1)
            full = reply + lrc
            self.log.debug(f"← {full.hex()}")
            return full
        raise IOError("No valid reply after retries")

    def _parse_reply(self, raw: bytes) -> bytes:
        if raw[0] != self.STX:
            raise IOError("Invalid STX")
        length = raw[1]
        payload = raw[2:2+length]
        if payload[-1] != self.ETX:
            raise IOError("Missing ETX")
        lrc_byte = raw[2+length]
        if self._lrc(raw[1:2+length+1]) != lrc_byte:
            raise IOError("LRC mismatch")
        # strip address byte + ETX
        return payload[1:-1]

    def read_block(self, block_type: int, block_number: int, byte_count: int) -> bytes:
        cmd = bytes([
            self.CMD_READ,
            block_type,
            block_number,
            (byte_count >> 8) & 0xFF,
            byte_count & 0xFF
        ])
        return self._parse_reply(self._send_frame(self._build_frame(cmd)))

    def write_block(self, block_type: int, block_number: int, data: bytes):
        header = bytes([
            self.CMD_WRITE,
            block_type,
            block_number,
            (len(data) >> 8) & 0xFF,
            len(data) & 0xFF
        ])
        self._parse_reply(self._send_frame(self._build_frame(header + data)))

    def info_block(self, block_number: int):
        """
        B_INFO directory command.
        Returns tuple (type_id, block_number, length_words).
        """
        cmd     = bytes([self.CMD_INFO, block_number])
        payload = self._parse_reply(self._send_frame(self._build_frame(cmd)))
        type_id      = payload[0]
        bn           = payload[1]
        length_words = (payload[-3] << 8) | payload[-2]
        return type_id, bn, length_words

class ExtendedAS511Client(AS511Client):
    def list_blocks(self, type_id: int, max_blocks: int = 256):
        found = []
        for bn in range(max_blocks):
            try:
                t, _, _ = self.info_block(bn)
                if t == type_id:
                    found.append(bn)
            except IOError:
                pass
        return found

    def download_blocks(self, type_id: int, out_dir: str):
        os.makedirs(out_dir, exist_ok=True)
        blocks = self.list_blocks(type_id)
        for bn in blocks:
            _, _, lw = self.info_block(bn)
            data     = self.read_block(type_id, bn, lw*2)
            path     = os.path.join(out_dir, f"block_{type_id:02X}_{bn}.bin")
            with open(path, "wb") as f:
                f.write(data)
            self.log.info(f"Saved block {bn} → {path}")
        return blocks

    def upload_blocks(self, type_id: int, in_dir: str):
        written = []
        prefix  = f"block_{type_id:02X}_"
        for fn in os.listdir(in_dir):
            if fn.startswith(prefix) and fn.endswith(".bin"):
                bn   = int(fn[len(prefix):-4])
                data = open(os.path.join(in_dir, fn), "rb").read()
                self.write_block(type_id, bn, data)
                self.log.info(f"Wrote block {bn} from {fn}")
                written.append(bn)
        return written

    def compare_block(self, type_id: int, bn: int, file_path: str):
        file_data = open(file_path, "rb").read()
        _, _, lw  = self.info_block(bn)
        plc_data  = self.read_block(type_id, bn, lw*2)

        def to_hex(buf):
            h = buf.hex()
            return [h[i:i+32] for i in range(0, len(h), 32)]

        return list(difflib.unified_diff(
            to_hex(plc_data),
            to_hex(file_data),
            fromfile=f"PLC_{bn}",
            tofile=os.path.basename(file_path),
            lineterm=""
        ))

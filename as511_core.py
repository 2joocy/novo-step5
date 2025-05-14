import serial
import time
import re

# AS511 protocol control characters
DLE = 0x10
STX = 0x02
ETX = 0x03
ACK = 0x06
NAK = 0x15

# Function code to name mapping
FUNCTION_CODES = {
    0x01: 'GET_IDENTIFICATION',
    0x02: 'INFO_BLOCK',
    0x03: 'READ_BLOCK',
    0x04: 'WRITE_BLOCK',
}

class AS511Client:
    def __init__(self, port, baudrate=9600, plc_address=1, timeout=1.0, max_retries=3):
        self.port = port
        self.baudrate = baudrate
        self.plc_address = plc_address
        self.timeout = timeout
        self.max_retries = max_retries
        self._ser = None
        self.connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self):
        try:
            self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            self._handshake()
            self.connected = True
        except serial.SerialException as e:
            raise RuntimeError(f"Connection failed: {e}")

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
        self.connected = False

    def calc_lrc(self, data: bytes) -> int:
        lrc = 0
        for b in data:
            lrc = (lrc + b) & 0xFF
        return ((~lrc + 1) & 0xFF)

    def _handshake(self):
        delay = 0.5
        for _ in range(self.max_retries):
            try:
                self._ser.write(bytes([DLE, STX, self.plc_address]))
                if self._ser.read(1) == bytes([ACK]):
                    return
            except serial.SerialException as e:
                raise RuntimeError(f"Handshake error: {e}")
            time.sleep(delay)
            delay *= 2
        raise RuntimeError("Handshake failed after retries")

    def _parse_block_id(self, block_id):
        """
        Accepts integer or string "DB65" or "DB65.1" and returns (block_number:int, bit_offset:int or None, friendly:str).
        """
        if isinstance(block_id, int):
            return block_id, None, f"DB{block_id}"
        m = re.match(r"DB(\d+)(?:\.(\d+))?$", str(block_id), re.IGNORECASE)
        if not m:
            raise ValueError(f"Invalid block identifier: {block_id}")
        blk = int(m.group(1))
        bit = int(m.group(2)) if m.group(2) is not None else None
        friendly = f"DB{blk}" + (f".{bit}" if bit is not None else "")
        return blk, bit, friendly

    def send_frame(self, func, payload=b""):
        body = bytes([func, self.plc_address]) + payload
        lrc = self.calc_lrc(body)
        frame = bytearray([DLE, STX]) + body + bytes([lrc, DLE, ETX])
        try:
            self._ser.write(frame)
        except serial.SerialException as e:
            raise RuntimeError(f"Write error: {e}")

    def read_frame(self):
        buf = bytearray()
        end = time.time() + self.timeout
        try:
            while time.time() < end:
                b = self._ser.read(1)
                if b:
                    buf += b
                    if len(buf) >= 3 and buf[-2:] == bytes([DLE, ETX]):
                        break
            else:
                raise RuntimeError("Read timeout")
        except serial.SerialException as e:
            raise RuntimeError(f"Read error: {e}")
        if buf[:2] != bytes([DLE, STX]):
            raise RuntimeError("Invalid frame header")
        body = buf[2:-2]
        *data, lrc = body
        if self.calc_lrc(bytes(data)) != lrc:
            raise RuntimeError("Checksum mismatch")
        return bytes(data)

    def get_identification(self):
        self.send_frame(0x01)
        func, type_id, major, minor, *rest = self.read_frame()
        return {
            'function': FUNCTION_CODES.get(func, hex(func)),
            'type_id': type_id,
            'major': major,
            'minor': minor,
            'info_raw': rest
        }

    def info_block(self, block_id):
        blk, bit, name = self._parse_block_id(block_id)
        self.send_frame(0x02, bytes([blk]))
        func, type_id, blk_num, length = self.read_frame()
        return {
            'function': FUNCTION_CODES.get(func, hex(func)),
            'block': name,
            'type_id': type_id,
            'length': length
        }

    def read_block(self, block_id):
        blk, bit, name = self._parse_block_id(block_id)
        try:
            self.send_frame(0x03, bytes([blk]))
            data = self.read_frame()
        finally:
            self._ser.reset_input_buffer()
        # data[0] is blk_num, following bytes are content
        content = data[1:]
        # present both decimal and hex
        values = list(content)
        hex_values = [hex(b) for b in content]
        return {
            'function': FUNCTION_CODES.get(data[0], hex(data[0])),
            'block': name,
            'values': values,
            'hex': hex_values
        }

    def write_block(self, block_id, data_bytes):
        blk, bit, name = self._parse_block_id(block_id)
        try:
            payload = bytes([blk]) + data_bytes
            self.send_frame(0x04, payload)
            resp = self.read_frame()
            ok = (resp and resp[0] == ACK)
        finally:
            self._ser.reset_input_buffer()
        return {
            'function': FUNCTION_CODES.get(resp[0] if resp else 0, hex(resp[0] if resp else 0)),
            'block': name,
            'success': ok
        }

    def compare_block(self, block_id, expected_type_id):
        info = self.info_block(block_id)
        return info['type_id'] == expected_type_id

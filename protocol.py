import struct
import time
from dataclasses import dataclass

# Header format:
# ver (B), msg_type (B), seq (I), timestamp (d), payload_len (H)
# ! = Network byte order (big-endian)
# B = unsigned char (1 byte)
# B = unsigned char (1 byte)
# I = unsigned int (4 bytes)
# d = double (8 bytes)
# H = unsigned short (2 bytes)
HEADER_FORMAT = "!BBIdH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

@dataclass
class Packet:
    ver: int
    msg_type: int
    seq: int
    timestamp: float
    payload: bytes

    def pack(self) -> bytes:
        """
        Serializes the packet into bytes.
        """
        payload_len = len(self.payload)
        header = struct.pack(
            HEADER_FORMAT,
            self.ver,
            self.msg_type,
            self.seq,
            self.timestamp,
            payload_len
        )
        return header + self.payload

    @classmethod
    def unpack(cls, data: bytes) -> 'Packet':
        """
        Deserializes bytes into a Packet object.
        Raises ValueError if data is too short or if payload length mismatch.
        """
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Data too short for header. Expected at least {HEADER_SIZE}, got {len(data)}")

        header_bytes = data[:HEADER_SIZE]
        ver, msg_type, seq, timestamp, payload_len = struct.unpack(HEADER_FORMAT, header_bytes)

        if len(data) < HEADER_SIZE + payload_len:
            raise ValueError(f"Data too short for payload. Expected {HEADER_SIZE + payload_len}, got {len(data)}")

        payload = data[HEADER_SIZE : HEADER_SIZE + payload_len]

        return cls(
            ver=ver,
            msg_type=msg_type,
            seq=seq,
            timestamp=timestamp,
            payload=payload
        )

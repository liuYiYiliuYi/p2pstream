import struct
from dataclasses import dataclass

# ChunkPayload Header: 
# frame_id (4 bytes, unsigned int)
# total_frags (2 bytes, unsigned short)
# frag_index (2 bytes, unsigned short)
PAYLOAD_HEADER_FORMAT = "!IHH"
PAYLOAD_HEADER_SIZE = struct.calcsize(PAYLOAD_HEADER_FORMAT)

@dataclass
class ChunkPayload:
    frame_id: int
    total_frags: int
    frag_index: int
    data: bytes

    def pack(self) -> bytes:
        """
        Serializes the chunk payload info + actual video data.
        """
        header = struct.pack(
            PAYLOAD_HEADER_FORMAT,
            self.frame_id,
            self.total_frags,
            self.frag_index
        )
        return header + self.data

    @classmethod
    def unpack(cls, buffer: bytes) -> 'ChunkPayload':
        """
        Deserializes bytes into ChunkPayload.
        """
        if len(buffer) < PAYLOAD_HEADER_SIZE:
            raise ValueError(f"Buffer too short for video payload header. Got {len(buffer)}")
            
        frame_id, total_frags, frag_index = struct.unpack(
            PAYLOAD_HEADER_FORMAT, 
            buffer[:PAYLOAD_HEADER_SIZE]
        )
        data = buffer[PAYLOAD_HEADER_SIZE:]
        
        return cls(frame_id, total_frags, frag_index, data)

# p2p_protocol.py

# Message Type Constants
TYPE_HANDSHAKE = 0x01   # New peer joining
TYPE_HEARTBEAT = 0x02   # Keep-alive
TYPE_BITMAP    = 0x03   # Broadcast available chunks
TYPE_REQUEST = 4      # Payload: chunk_seq (int)
TYPE_DATA = 5         # Payload: data bytes
TYPE_PEER_LIST = 6    # Payload: JSON list of [host, port, role]
TYPE_PING = 7         # Payload: timestamp (float)
TYPE_PONG = 8         # Payload: echo timestamp (float)
TYPE_STATS_REPORT = 9 # Payload: JSON stats from peer

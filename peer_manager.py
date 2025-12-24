import time
from typing import Dict, Set

class Peer:
    def __init__(self, host: str, port: int, role: str = "viewer"):
        self.host = host
        self.port = port
        self.role = role
        self.last_seen = time.time()
        self.remote_bitmap: Set[int] = set()

    def update_seen(self):
        self.last_seen = time.time()

    def update_bitmap(self, bitmap_data: Set[int]):
        self.remote_bitmap = bitmap_data

    def set_role(self, role: str):
        self.role = role

    def __repr__(self):
        return f"<Peer {self.host}:{self.port} ({self.role})>"

class PeerManager:
    def __init__(self):
        self.peers: Dict[tuple, Peer] = {} # (host, port) -> Peer

    def update_peer(self, addr: tuple, role: str = None):
        """
        Updates an existing peer's last_seen, or adds a new peer.
        If role is provided, updates role.
        """
        host, port = addr
        if addr not in self.peers:
            # Default role is viewer until told otherwise
            self.peers[addr] = Peer(host, port, role if role else "viewer")
        else:
            self.peers[addr].update_seen()
            if role:
                self.peers[addr].set_role(role)

    def update_bitmap(self, addr: tuple, bitmap_data: Set[int]):
        """
        Updates the bitmap for the given peer address.
        """
        if addr in self.peers:
            self.peers[addr].update_bitmap(bitmap_data)
        else:
            # If we receive a bitmap from an unknown peer, we might want to Add them or Ignore.
            # For simplicity, let's add them implicitly or ensure Handshake happened first.
            # design choice: add them implicitly to be robust.
            self.update_peer(addr)
            self.peers[addr].update_bitmap(bitmap_data)

    def get_peer(self, addr: tuple) -> Peer:
        return self.peers.get(addr)
    
    def get_active_peers(self) -> Dict[tuple, Peer]:
        return self.peers

    def prune_dead_peers(self, timeout: float = 5.0):
        """
        Removes peers that haven't been seen for 'timeout' seconds.
        """
        now = time.time()
        dead_peers = [addr for addr, peer in self.peers.items() if now - peer.last_seen > timeout]
        for addr in dead_peers:
            del self.peers[addr]
        return dead_peers

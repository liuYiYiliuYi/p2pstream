import logging
import time
import random
import json
from enum import Enum
from typing import Set, Dict, List, Optional, Tuple, Any

import p2p_protocol as P2P
from protocol import Packet

logger = logging.getLogger(__name__)

class P2PAlgorithm:
    """
    Abstract Base Class for P2P Strategies.
    Decouples logic from the low-level P2PNode transport.
    """
    def __init__(self, node):
        self.node = node # Reference to P2PNode for accessing transport, peer_manager, store
    
    def on_start(self):
        """Called when P2PNode starts."""
        pass

    def on_tick(self):
        """Called periodically (e.g. 10Hz) for scheduling logic."""
        pass
    
    def handle_packet(self, packet: Packet, addr: tuple) -> bool:
        """
        Handle incoming packets. 
        Returns True if handled, False if P2PNode should handle default logic.
        """
        return False

    def on_chunk_received(self, chunk_id: int, payload: bytes, source_addr: tuple):
        """Called when a new DATA chunk is successfully validated and stored."""
        pass

    def on_peer_discovered(self, addr: tuple):
        """Called when a new peer is connected."""
        pass

class SplitterAlgorithm(P2PAlgorithm):
    """
    Broadcaster Logic: Round-Robin Source Seeding.
    """
    def __init__(self, node):
        super().__init__(node)
        self.rr_index = 0
    
    def on_chunk_generated(self, chunk_id: int, payload: bytes):
        """
        Special hook for Broadcaster: Active Push (Round-Robin).
        """
        peers = list(self.node.peer_manager.get_active_peers().keys())
        if not peers:
            return

        # Round Robin Selection
        self.rr_index = (self.rr_index + 1) % len(peers)
        target = peers[self.rr_index]
        
        self.node.send_data_packet(target, chunk_id, payload)
        # logger.debug(f"Splitter: Distributed chunk {chunk_id} to {target}")

    def on_tick(self):
        # Splitter doesn't need to fetch anything.
        pass

class DefaultPushAlgorithm(P2PAlgorithm):
    """
    Peer Logic: Pure Push (Flooding).
    """
    def __init__(self, node):
        super().__init__(node)
        self.pending_push = {} # chunk_id -> set(target_addrs)
    
    def on_chunk_received(self, chunk_id: int, payload: bytes, source_addr: tuple):
        # FLOOD: Schedule this chunk to be sent to ALL neighbors (except source)
        peers = self.node.peer_manager.get_active_peers()
        targets = [p for p in peers if p != source_addr]
        
        if targets:
            # logger.debug(f"PushAlgo: Flooding chunk {chunk_id} to {len(targets)} peers")
            self.pending_push[chunk_id] = targets

    def on_tick(self):
        # Process Pending Push Queue
        # Simple FIFO or random selection to drain queue
        if not self.pending_push:
            return
            
        # Process a few pushes per tick
        processed = 0
        limit = 5 
        
        # Snapshot to iterate
        keys = list(self.pending_push.keys())
        for chunk_id in keys:
            targets = self.pending_push[chunk_id]
            if not targets:
                del self.pending_push[chunk_id]
                continue
                
            # Pop one target
            target = targets.pop(0)
            
            # Send
            # We assume node has the data since we just received it
            # But we should use safe send
            self.node.send_data(target, chunk_id)
            processed += 1
            
            if not targets:
                del self.pending_push[chunk_id]
                

class RarestFirstAlgorithm(DefaultPushAlgorithm):
    """
    Peer Logic: Hybrid (Push + Pull Rarest).
    Inherits Push logic from DefaultPushAlgorithm.
    Adds Pull logic for rarest chunks.
    """
    def __init__(self, node):
        super().__init__(node)
        self.pull_window = 50 # Look ahead K chunks
        
    def handle_packet(self, packet: Packet, addr: tuple) -> bool:
        """
        Intercept REQUEST to perform Deduplication (ALGO.md 3.2.3)
        """
        if packet.msg_type == P2P.TYPE_REQUEST:
            try:
                seq_requested = int(packet.payload.decode('utf-8'))
                
                # Critical Dedup: Check if this chunk was already queued to be PUSHED to this peer
                # If so, remove from Push queue (because we are about to send it as Response)
                if seq_requested in self.pending_push:
                    targets = self.pending_push[seq_requested]
                    if addr in targets:
                        # logger.debug(f"Dedup: Peer {addr} requested chunk {seq_requested} which was in Push Queue. Promoting.")
                        targets.remove(addr)
                        if not targets:
                            del self.pending_push[seq_requested]
                            
                # Let P2PNode handle the actual send_data
                return False 
            except:
                pass
        
        return super().handle_packet(packet, addr)

    
    def on_tick(self):
        # 1. Run Default Push Logic first
        super().on_tick()

        # 2. Run Pull Logic (Rarest First)
        # Use Scheduler-like logic but specifically for Rarest First
        current_bitmap = self.node.my_bitmap
        if not current_bitmap:
            return

        # Simple Playback Head estimation: Max chunk - 5? 
        # Or just look at missing chunks in the known range.
        # Let's target missing chunks in the [Max-Window, Max] range for now as a heuristic of 'relevant' chunks.
        max_chunk = max(current_bitmap)
        start_scan = max(0, max_chunk - self.pull_window)
        end_scan = max_chunk + 10 # Look a bit ahead too
        
        needed_chunks = set()
        for i in range(start_scan, end_scan):
            if i not in current_bitmap:
                needed_chunks.add(i)
        
        if not needed_chunks:
            return

        # Calculate Availability (Rarity)
        peers = self.node.peer_manager.get_active_peers()
        if not peers:
            return
            
        rarity_map = {} # chunk_id -> list of owners
        for c in needed_chunks:
            owners = []
            for addr, peer in peers.items():
                if c in peer.remote_bitmap:
                    owners.append(addr)
            if owners:
                rarity_map[c] = owners
        
        # Sort by rarity (fewest owners first)
        sorted_chunks = sorted(rarity_map.keys(), key=lambda c: len(rarity_map[c]))
        
        # Request top K rarest
        limit_requests = 5
        sent_requests = 0
        
        for c in sorted_chunks:
            owners = rarity_map[c]
            target = random.choice(owners)
            
            # Send Request
            payload = str(c).encode('utf-8')
            packet = Packet(ver=1, msg_type=P2P.TYPE_REQUEST, seq=0, timestamp=time.time(), payload=payload)
            self.node.transport.send_packet(packet, target)
            sent_requests += 1
            
            if sent_requests >= limit_requests:
                break

class EDFAlgorithm(DefaultPushAlgorithm):
    """
    Peer Logic: Hybrid (Push + Pull EDF).
    Prioritize earliest deadline (closest to playback).
    """
    def __init__(self, node):
        super().__init__(node)
        self.pull_window = 50
        
    def handle_packet(self, packet: Packet, addr: tuple) -> bool:
        """
        Intercept REQUEST to perform Deduplication (ALGO.md 3.2.3)
        Similar to RarestFirstAlgorithm.
        """
        if packet.msg_type == P2P.TYPE_REQUEST:
            try:
                seq_requested = int(packet.payload.decode('utf-8'))
                if seq_requested in self.pending_push:
                    targets = self.pending_push[seq_requested]
                    if addr in targets:
                        targets.remove(addr)
                        if not targets:
                            del self.pending_push[seq_requested]
                return False 
            except:
                pass
        
        return super().handle_packet(packet, addr)

    
    def on_tick(self):
        # 1. Run Push
        super().on_tick()
        
        # 2. Run Pull (EDF)
        current_bitmap = self.node.my_bitmap
        if not current_bitmap:
            return
            
        # Estimate Playback deadline. 
        # We need the "Next Missing Chunk" after the continuous block.
        # Simple heuristic: Start from min(bitmap) or (max - buffer_size).
        # Let's assume we are playing near max-delay
        max_chunk = max(current_bitmap)
        start_scan = max(0, max_chunk - self.pull_window)
        
        # Find FIRST missing chunk (Earliest Deadline)
        target_chunk = -1
        for i in range(start_scan, max_chunk + 10):
            if i not in current_bitmap:
                # Check if anyone has it
                peers = self.node.peer_manager.get_active_peers()
                owners = [addr for addr, p in peers.items() if i in p.remote_bitmap]
                if owners:
                    target_chunk = i
                    target_peer = random.choice(owners)
                    
                    # Send Request IMMEDIATELY and stop (EDF focuses on the most urgent)
                    payload = str(target_chunk).encode('utf-8')
                    packet = Packet(ver=1, msg_type=P2P.TYPE_REQUEST, seq=0, timestamp=time.time(), payload=payload)
                    self.node.transport.send_packet(packet, target_peer)
                    
                    # logger.debug(f"EDF: Urgent Request {target_chunk} from {target_peer}")
                    return # Only request the most urgent one per tick? Or a few?
                    # algo says "break # 只请求最急的一个"
        


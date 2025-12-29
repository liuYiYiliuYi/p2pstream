import asyncio
import time
import json
import logging
import random
import socket
from typing import Set, Dict, Optional

from protocol import Packet
from transport import UDPTransport
from peer_manager import PeerManager
import p2p_protocol as P2P

logger = logging.getLogger(__name__)

class P2PNode:
    def __init__(self, host: str, port: int, role: str = "viewer", initial_chunks: Optional[Set[int]] = None):
        self.host = host
        self.port = port
        self.role = role
        self.my_bitmap: Set[int] = initial_chunks if initial_chunks else set()
        self.data_store: Dict[int, bytes] = {} # seq -> data
        
        # Initialize data_store with dummy data for initial chunks
        for seq in self.my_bitmap:
            self.data_store[seq] = f"Data-{seq}".encode()

        self.transport = UDPTransport(on_packet_received=self.handle_packet)
        self.peer_manager = PeerManager()
        self.running = False

    async def start(self):
        self.running = True
        await self.transport.start_server(self.host, self.port)
        logger.info(f"P2PNode started on {self.host}:{self.port}")
        
        # Start background tasks
        asyncio.create_task(self.loop_heartbeat())
        asyncio.create_task(self.loop_broadcast_bitmap())
        asyncio.create_task(self.loop_schedule_fetch())
        asyncio.create_task(self.loop_prune_peers())
        asyncio.create_task(self.loop_pex())

    async def stop(self):
        self.running = False
        self.transport.close()

    def connect_to(self, host: str, port: int):
        """
        Manually send a handshake to a known peer to bootstrap connection.
        """
        payload = json.dumps({"role": self.role}).encode('utf-8')
        packet = Packet(
            ver=1,
            msg_type=P2P.TYPE_HANDSHAKE,
            seq=0,
            timestamp=time.time(),
            payload=payload
        )
        self.transport.send_packet(packet, (host, port))
        logger.info(f"Sent Handshake to {host}:{port} as {self.role}")

    def handle_packet(self, packet: Packet, addr: tuple):
        """
        Callback from UDPTransport. Dispatches based on msg_type.
        """
        # Always update peer liveness
        self.peer_manager.update_peer(addr)

        if packet.msg_type == P2P.TYPE_HANDSHAKE:
            # Parse Role if present
            try:
                if packet.payload:
                    data = json.loads(packet.payload.decode('utf-8'))
                    remote_role = data.get("role", "viewer")
                    self.peer_manager.update_peer(addr, role=remote_role)
                else:
                    self.peer_manager.update_peer(addr, role="viewer")
            except:
                self.peer_manager.update_peer(addr, role="viewer")

            logger.info(f"Received HANDSHAKE from {addr}")
            # Reply with bitmap so they know what we have immediately
            self.send_bitmap(addr)
            
            # PEX: If we are broadcaster, send our peer list to the new joiner immediately
            if self.role == "broadcaster":
                self.send_peer_list(addr)

        elif packet.msg_type == P2P.TYPE_PEER_LIST:
            try:
                # Payload: [[host, port, role], ...]
                peers_list = json.loads(packet.payload.decode('utf-8'))
                my_addr = (self.host, self.port) # Note: this might be 0.0.0.0, which matches nothing usually.
                # Better check: Don't connect to self loopback if we are testing locally.
                
                count_new = 0
                for host, port, role in peers_list:
                    # Ignore self (simple check)
                    if port == self.port: 
                        continue
                    
                    # Ignore localhost/0.0.0.0 if we got it (should actaually filter at source, but safety here)
                    if host.startswith("127.") or host == "0.0.0.0" or host == "localhost":
                         # If we are seemingly local, try to connect to localhost? No, usually bad in prod.
                         # But for local testing it helps.
                         pass

                    
                    # Connect if not already connected
                    if (host, port) not in self.peer_manager.peers:
                        logger.info(f"PEX: Discovered new peer {host}:{port} ({role}). Connecting...")
                        self.connect_to(host, port)
                        count_new += 1
                        
                if count_new > 0:
                    logger.info(f"PEX: Connected to {count_new} new peers.")
            except Exception as e:
                logger.error(f"PEX parse error from {addr}: {e}")

        elif packet.msg_type == P2P.TYPE_PING:
            # Reply with PONG, echoing the payload (timestamp)
            try:
                pong = Packet(ver=1, msg_type=P2P.TYPE_PONG, seq=0, timestamp=time.time(), payload=packet.payload)
                self.transport.send_packet(pong, addr)
            except:
                pass

        elif packet.msg_type == P2P.TYPE_PONG:
            try:
                sent_time = float(packet.payload.decode('utf-8'))
                rtt = time.time() - sent_time
                if addr in self.peer_manager.peers:
                    self.peer_manager.peers[addr].update_rtt(rtt)
                    # logger.debug(f"RTT to {addr}: {rtt*1000:.1f}ms")
            except:
                pass

        elif packet.msg_type == P2P.TYPE_HEARTBEAT:
            # Just updates liveness (handled above)
            pass

        elif packet.msg_type == P2P.TYPE_BITMAP:
            try:
                data = json.loads(packet.payload.decode('utf-8'))
                new_set = set()
                # Check for range format [[s, e], ...]
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                    for s, e in data:
                        new_set.update(range(s, e + 1))
                else:
                    new_set = set(data)
                
                self.peer_manager.update_bitmap(addr, new_set)
            except Exception as e:
                logger.error(f"Bitmap parse error {addr}: {e}")

        elif packet.msg_type == P2P.TYPE_REQUEST:
            try:
                seq_requested = int(packet.payload.decode('utf-8'))
                if seq_requested in self.data_store:
                    self.send_data(addr, seq_requested)
                    logger.info(f"Fulfilled REQUEST for chunk {seq_requested} from {addr}")
                else:
                    logger.warning(f"Peer {addr} requested chunk {seq_requested} which I don't have.")
            except Exception as e:
                logger.error(f"Failed to handle request from {addr}: {e}")

        elif packet.msg_type == P2P.TYPE_DATA:
            seq = packet.seq
            if seq not in self.my_bitmap:
                self.data_store[seq] = packet.payload
                self.my_bitmap.add(seq)
                logger.info(f"Received DATA chunk {seq} from {addr}")
                # Ideally, broadcast new bitmap or just let next periodic broadcast handle it
            else:
                logger.debug(f"Received duplicate chunk {seq} from {addr}")

    def send_bitmap(self, addr: tuple):
        """
        Sends bitmap using RLE Range Compression: [[start, end], ...]
        """
        if not self.my_bitmap:
            payload = b"[]"
        else:
            sorted_chunks = sorted(list(self.my_bitmap))
            ranges = []
            if sorted_chunks:
                start = sorted_chunks[0]
                prev = sorted_chunks[0]
                for x in sorted_chunks[1:]:
                    if x == prev + 1:
                        prev = x
                    else:
                        ranges.append([start, prev])
                        start = x
                        prev = x
                ranges.append([start, prev])
            
            # Limit ranges to safe UDP size (e.g., 200 ranges ~ 4KB)
            if len(ranges) > 200:
                ranges = ranges[-200:]
            
            payload = json.dumps(ranges).encode('utf-8')
        
        try:
            packet = Packet(
                ver=1, msg_type=P2P.TYPE_BITMAP, seq=0, 
                timestamp=time.time(), payload=payload
            )
            self.transport.send_packet(packet, addr)
        except ValueError as e:
            logger.error(f"Bitmap send error {addr}: {e}")

    def send_peer_list(self, addr: tuple):
        peers = self.peer_manager.get_active_peers()
        peer_list_data = []
        for p_addr, peer in peers.items():
            peer_list_data.append([peer.host, peer.port, peer.role])
        
        # Add Self to the list so the new joiner knows about me (the broadcaster/sender)
        # But we must send our ACTUAL IP, not 0.0.0.0
        my_ip = self.get_best_ip_for_peer(addr[0])
        peer_list_data.append([my_ip, self.port, self.role])

        payload = json.dumps(peer_list_data).encode('utf-8')
        packet = Packet(ver=1, msg_type=P2P.TYPE_PEER_LIST, seq=0, timestamp=time.time(), payload=payload)
        self.transport.send_packet(packet, addr)

    def get_best_ip_for_peer(self, peer_ip: str) -> str:
        """
        Attempts to find the most reachable IP for a given peer.
        If peer is local, return 127.0.0.1.
        Otherwise return LAN IP.
        """
        if peer_ip == "127.0.0.1" or peer_ip == "localhost":
            return "127.0.0.1"
        
        # Try to find a socket route
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((peer_ip, 1)) # Dummy connect
            return s.getsockname()[0]
        except:
            return "0.0.0.0" # Fallback
        finally:
            if s: s.close()


    def send_data(self, addr: tuple, seq: int):
        data = self.data_store.get(seq, b"")
        packet = Packet(
            ver=1,
            msg_type=P2P.TYPE_DATA,
            seq=seq,
            timestamp=time.time(),
            payload=data
        )
        self.transport.send_packet(packet, addr)

    async def loop_heartbeat(self):
        """
        Periodically send heartbeat to all peers.
        """
        while self.running:
            await asyncio.sleep(2.0)
            peers = self.peer_manager.get_active_peers()
            
            # Stats Integration
            from stats_manager import StatsManager
            # Pass list of (host, port) tuples
            StatsManager().update_peers(list(peers.keys()))
            
            # Additional Stats: Avg RTT
            total_rtt = 0
            count = 0
            for p in peers.values():
                if p.rtt > 0:
                    total_rtt += p.rtt
                    count += 1
            avg_rtt_ms = (total_rtt / count * 1000) if count > 0 else 0
            StatsManager().update_network_quality(avg_rtt_ms)

            if not peers:
                continue
            
            # Send Heartbeat AND Ping
            packet_hb = Packet(ver=1, msg_type=P2P.TYPE_HEARTBEAT, seq=0, timestamp=time.time(), payload=b"")
            payload_ping = str(time.time()).encode('utf-8')
            packet_ping = Packet(ver=1, msg_type=P2P.TYPE_PING, seq=0, timestamp=time.time(), payload=payload_ping)

            for addr in peers:
                self.transport.send_packet(packet_hb, addr)
                self.transport.send_packet(packet_ping, addr)

    async def loop_pex(self):
        """
        Periodically broadcast Peer List to all neighbors.
        This helps Viewers discover each other.
        """
        while self.running:
            await asyncio.sleep(5.0) # Every 5 seconds
            
            # Only Broadcaster needs to be the main source of truth, 
            # but Viewers can also share gossip. Let's let everyone share.
            # But usually Broadcaster has the full view.
            
            peers = self.peer_manager.get_active_peers()
            if not peers:
                continue
            
            # Construct Peer List: [[host, port, role], ...]
            # Note: We need to send how *others* can verify them.
            # In a real NAT scenario, we'd send the IP we see them as.
            peer_list_data = []
            for addr, peer in peers.items():
                peer_list_data.append([peer.host, peer.port, peer.role])
                
            # Add self
            # But wait, self IP depends on who we are talking to if we have multiple NICs.
            # For simplicity, we calculate best IP for each target? No, expensive.
            # Let's just use a generic LAN IP.
            # Better strategy: for each neighbor, send specific list? 
            # Or just append "me" dynamically in the send loop.
            
            for addr in peers:
                try:
                    # Dynamically add SELF to the list for this specific target
                    my_ip = self.get_best_ip_for_peer(addr[0])
                    # Copy list
                    final_list = list(peer_list_data)
                    final_list.append([my_ip, self.port, self.role])
                    
                    payload = json.dumps(final_list).encode('utf-8')
                    packet = Packet(ver=1, msg_type=P2P.TYPE_PEER_LIST, seq=0, timestamp=time.time(), payload=payload)
            
                    self.transport.send_packet(packet, addr)
                except:
                    pass

    async def loop_broadcast_bitmap(self):
        """
        Periodically broadcast bitmap to all peers.
        """
        while self.running:
            await asyncio.sleep(0.2) # 5Hz broadcast (Fast Update for P2P)
            
            # Stats Integration
            from stats_manager import StatsManager
            # Simple summary: "105 chunks (101-205)"
            if self.my_bitmap:
                min_c = min(self.my_bitmap)
                max_c = max(self.my_bitmap)
                summary = f"{len(self.my_bitmap)} chunks ({min_c}-{max_c})"
            else:
                summary = "0 chunks"
            StatsManager().update_bitmap(summary)

            peers = self.peer_manager.get_active_peers()
            for addr in peers:
                self.send_bitmap(addr)

    async def loop_prune_peers(self):
        while self.running:
            await asyncio.sleep(5.0)
            dead_peers = self.peer_manager.prune_dead_peers()
            if dead_peers:
                logger.info(f"Pruned dead peers: {dead_peers}")

    async def loop_schedule_fetch(self):
        """
        Uses P2PScheduler to decide what to fetch.
        """
        # Lazy import to avoid circular dependency if any
        from scheduler import P2PScheduler
        scheduler = P2PScheduler()

        while self.running:
            # Check more frequently for lower latency
            await asyncio.sleep(0.1) 
            
            # Use Scheduler to get fetch plan
            peers = self.peer_manager.get_active_peers()
            requests = scheduler.schedule(self.my_bitmap, peers)
            
            for chunk_id, target_peer in requests:
                payload = str(chunk_id).encode('utf-8')
                packet = Packet(
                    ver=1,
                    msg_type=P2P.TYPE_REQUEST,
                    seq=0,
                    timestamp=time.time(),
                    payload=payload
                )
                self.transport.send_packet(packet, target_peer)
                logger.debug(f"Requested chunk {chunk_id} from {target_peer}") # Reduced log level
                
            # Sleep less to be more responsive
            await asyncio.sleep(0.05)

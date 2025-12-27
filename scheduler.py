import random
from typing import Dict, Set, List, Tuple
import logging

logger = logging.getLogger(__name__)

class P2PScheduler:
    """
    Abstracts the logic of deciding which chunks to fetch and from whom.
    """
    def __init__(self):
        pass

    def schedule(self, 
                 my_bitmap: Set[int], 
                 peers: Dict[tuple, object]) -> List[Tuple[int, tuple]]:
        """
        Decides a list of (chunk_id, peer_addr) to request.
        
        Args:
            my_bitmap: Set of chunk IDs I already have.
            peers: Dict of {addr: PeerObj} from PeerManager.
            
        Returns:
            List of (chunk_id, target_peer_addr) tuples.
        """
        if not peers:
            return []

        # 1. Identify all chunks available in the network that I don't have
        available_unknown_chunks = set()
        chunk_owners: Dict[int, List[tuple]] = {} # seq -> list of owner_addrs

        for addr, peer in peers.items():
            remote_chunks = peer.remote_bitmap
            new_chunks = remote_chunks - my_bitmap
            available_unknown_chunks.update(new_chunks)
            
            for c in new_chunks:
                if c not in chunk_owners:
                    chunk_owners[c] = []
                chunk_owners[c].append(addr)

        if not available_unknown_chunks:
            return []

        # 2. Strategy: Sequential / Latency-First (Reverse Sort)
        sorted_chunks = sorted(list(available_unknown_chunks), reverse=True)
        
        # Rate Limit / Batch Size
        batch_size = 20
        chunks_to_process = sorted_chunks[:batch_size]
        
        requests = []
        
        for chunk_id in chunks_to_process:
            owners = chunk_owners[chunk_id]
            
            viewers = []
            broadcasters = []
            
            for o_addr in owners:
                # We need to access peer.role. 
                # The 'peers' dict value is expected to have a 'role' attribute.
                peer = peers.get(o_addr)
                if peer and hasattr(peer, 'role') and peer.role == "viewer":
                    viewers.append(o_addr)
                else:
                    broadcasters.append(o_addr)
            
            target_peer = None
            
            # 3. Server Offloading & Backoff Logic
            if viewers:
                # If viewers have it, prioritizing viewers is mandatory
                target_peer = random.choice(viewers)
            elif broadcasters:
                # Broadcaster Backoff:
                # If only Broadcaster has it, mostly wait for peers to get it.
                # 90% chance to skip if only broadcaster has it.
                if random.random() < 0.9:
                     continue
                target_peer = random.choice(broadcasters)
            
            if target_peer:
                requests.append((chunk_id, target_peer))
                
        return requests

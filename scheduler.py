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
        batch_size = 100 # Increased from 20 to support ~20FPS video
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
            
            # 3. Strategy: P2P Optimization
            if viewers:
                # Ideal case: Viewers have it. Always prefer them.
                target_peer = random.choice(viewers)
                # logger.debug(f"Chunk {chunk_id}: Found {len(viewers)} viewers. Selected {target_peer}")
            elif broadcasters:
                # Fallback case: Only Broadcaster has it.
                
                # SMART BACKOFF LOGIC:
                # If we rely too much on Broadcaster, P2P ratio drops.
                # But if we wait too long, video lags.
                
                # Rule:
                # 1. If I am the ONLY viewer (implied if I can't find other viewers for *any* chunk, but here purely local decision),
                #    then I must download from Broadcaster.
                # 2. If there are other viewers (but they just don't have this chunk YET),
                #    we should wait a bit to see if they get it (P2P opportunity).
                
                # Heuristic: 
                # If we are "caught up" (fetching recent chunks), we can afford to wait.
                # If we are "lagging" (fetching old chunks), we must fetch ASAP.
                
                # For now, let's use a simpler Probabilistic Backoff that is LESS AGGRESSIVE than before.
                # 30% chance to wait (skip) if only broadcaster keeps it. 
                # This encourages P2P propagation without stalling the stream too hard.
                if random.random() < 0.3:
                     # logger.debug(f"Chunk {chunk_id}: Backoff from Broadcaster to wait for peers.")
                     continue
                
                target_peer = random.choice(broadcasters)
                # logger.debug(f"Chunk {chunk_id}: Fallback to Broadcaster {target_peer}")
            
            if target_peer:
                requests.append((chunk_id, target_peer))
                
        return requests

import asyncio
import socket
import argparse
import logging
import cv2
import time
from typing import Optional

from p2p_node import P2PNode
from dashboard import start_dashboard
from video_source import ScreenCapturer, FrameFragmenter
from video_player import FrameReassembler, VideoRenderer
import p2p_protocol as P2P
from protocol import Packet

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("p2p_node.log", mode='w')
    ]
)
logger = logging.getLogger("Main")

async def broadcaster_loop(node: P2PNode):
    """
    Broadcaster Logic: Capture -> Fragment -> Store/Broadcast
    """
    capturer = ScreenCapturer(width=640, height=480)
    current_frame_id = 0
    
    logger.info("Starting Broadcaster Loop...")
    
    while True:
        # 1. Capture
        frame_bytes = capturer.capture_frame()
        if not frame_bytes:
            await asyncio.sleep(0.1)
            continue
            
        current_frame_id += 1
        
        # 2. Fragment
        chunks = FrameFragmenter.fragment(current_frame_id, frame_bytes)
        
        # 3. Store in P2P Node
        new_chunk_ids = set()
        for chunk_id, payload in chunks:
            # We bypass the network for ourselves and inject directly into data_store
            # Note: We need to strip the L1 Header part if we were using send_packet,
            # but P2PNode expects raw payload in data_store if we are the source.
            # Wait, P2PNode.data_store stores the P2P PAYLOAD (Layer 2 payload).
            # Layer 2 payload for TYPE_DATA is just the raw bytes?
            # Let's check p2p_node.py:
            #   self.data_store[seq] = packet.payload
            #   And send_data uses: packet.payload = data
            # So yes, we store the packed Layer 3 payload (ChunkPayload) directly into data_store.
            node.data_store[chunk_id] = payload
            new_chunk_ids.add(chunk_id)
            
        # 4. Update my_bitmap
        node.my_bitmap.update(new_chunk_ids)
        
        # 5. Clean up old frames
        # Remove frames older than 1000 frames (approx 50 seconds at 20fps)
        # This gives plenty of time for new peers to catch up or for retransmissions.
        if current_frame_id > 1000:
            old_frame_id = current_frame_id - 1000
            # Rough cleanup: chunks are frame_id * 1000 + frag_index
            # Calculate range of chunk IDs to remove
            start_chunk = old_frame_id * 1000
            end_chunk = (old_frame_id + 1) * 1000
            
            # Identify chunks to remove
            to_remove = [c for c in node.data_store.keys() if start_chunk <= c < end_chunk]
            for c in to_remove:
                del node.data_store[c]
                if c in node.my_bitmap:
                    node.my_bitmap.remove(c)
        await asyncio.sleep(0.05)

async def viewer_loop(node: P2PNode):
    """
    Viewer Logic: Poll P2PNode data_store -> Reassemble -> Render
    """
    reassembler = FrameReassembler()
    renderer = VideoRenderer("P2P Stream Viewer")
    
    logger.info("Starting Viewer Loop...")
    
    # We maintain a set of 'processed' chunk IDs to avoid re-processing
    processed_chunks = set()
    
    while True:
        # Check P2PNode for new chunks
        # Because P2PNode runs in background, it populates node.data_store
        
        # Find chunks we have in data store but haven't fed to reassembler
        # Optimziation: In a high perfrormance system, P2PNode would push to a Queue.
        # Here we poll for simplicity.
        
        available_ids = set(node.data_store.keys())
        new_ids = available_ids - processed_chunks
        
        if new_ids:
            for chunk_id in new_ids:
                payload = node.data_store[chunk_id]
                processed_chunks.add(chunk_id)
                
                # Feed to reassembler
                jpeg_frame = reassembler.add_fragment(payload)
                if jpeg_frame:
                    # We got a full frame! Render it!
                    renderer.render(jpeg_frame)

        # Important: CV2 UI update
        # cv2.waitKey(1) is called inside renderer.render, 
        # but if no frames arrive, we still need to pump the UI loop occasionally?
        # Not strictly necessary if we rely on render calls, but good for responsiveness.
        # However, to avoid 'Not Responding' on Mac, we explicitly waitKey here if idle.
        if not new_ids:
            cv2.waitKey(1) 

        await asyncio.sleep(0.01)

def get_lan_ips():
    ips = []
    # Method 1: Connect generic (gives default route interface)
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
        if not ip.startswith('127.'):
            ips.append(f"{ip} (Default)")
    except Exception:
        pass
    finally:
        if s:
            s.close()
            
    # Method 2: Iterate interfaces (better for multi-homed or VPN)
    try:
        # getaddrinfo with empty host returns all
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.') and ip not in [x.split()[0] for x in ips]:
                ips.append(ip)
    except Exception:
        pass
        
    return ips if ips else ['127.0.0.1']

async def main():
    parser = argparse.ArgumentParser(description="P2P Video Streaming Node")
    parser.add_argument('--role', choices=['broadcaster', 'viewer'], required=True, help="Node role")
    parser.add_argument('--port', type=int, required=True, help="UDP Port to bind")
    parser.add_argument('--connect', type=str, help="Initial peer to connect to (host:port)")
    
    args = parser.parse_args()
    
    # Print Multi-machine info
    lan_ips = get_lan_ips()
    logger.info(f"==================================================")
    logger.info(f"System Running as {args.role.upper()} on port {args.port}")
    logger.info(f"Available IPs: {lan_ips}")
    logger.info(f"If connecting from another machine, try the one that looks like 192.168.x.x or 172.20.x.x")
    logger.info(f"==================================================")
    
    # 1. Start P2P Node
    host = "0.0.0.0" # Bind all interfaces
    node = P2PNode(host, args.port, role=args.role)
    await node.start()
    
    # 2. Connect to peer if specified
    if args.connect:
        target_host, target_port = args.connect.split(":")
        node.connect_to(target_host, int(target_port))
        
    # 3. Start Dashboard
    await start_dashboard(args.port) # Serve dashboard on same port for convenience? 
    # Ah, dashboard uses TCP, P2P uses UDP. So we CAN use the same port number! Perfect.
    
    # 4. Start Role-Specific Task
    if args.role == "broadcaster":
        # Use simpler window flag for better cross-platform compatibility
        cv2.namedWindow("Broadcaster Monitor", cv2.WINDOW_AUTOSIZE) 
        asyncio.create_task(broadcaster_loop(node))
    else:
        asyncio.create_task(viewer_loop(node))
        
    logger.info(f"System Running as {args.role.upper()} on port {args.port}")
    
    # Keep alive
    try:
        # We need a living loop that allows interruptions
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await node.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

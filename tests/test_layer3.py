import logging
import random
import sys
import os
import cv2
import numpy as np

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from video_source import ScreenCapturer, FrameFragmenter
from video_player import FrameReassembler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("TestLayer3")

def test_media_pipeline():
    logger.info("Initializing Media Pipeline Test...")
    
    # 1. Capture
    capturer = ScreenCapturer(width=640, height=480)
    frame_bytes = capturer.capture_frame()
    
    if not frame_bytes:
        logger.error("Capture failed! Is mss working?")
        return # Skip if capture fails (e.g. headless)

    original_len = len(frame_bytes)
    logger.info(f"Captured Frame: {original_len} bytes")

    # 2. Fragment
    frame_id = 42
    chunks = FrameFragmenter.fragment(frame_id, frame_bytes)
    logger.info(f"Fragmented into {len(chunks)} chunks")
    
    # 3. Simulate Network: Shuffle
    # Split chunks into (id, payload) -> just payload is needed for reassembler input in this direct test?
    # No, reassembler.add_fragment takes the packed payload bytes (which includes L3 header + video data)
    # The `chunks` list from fragment() is [(chunk_id, packed_payload_bytes)]
    shuffled_payloads = [c[1] for c in chunks]
    random.shuffle(shuffled_payloads)
    logger.info("Shuffled fragments to simulate out-of-order delivery")

    # 4. Reassemble
    reassembler = FrameReassembler()
    
    reassembled_frame = None
    for i, payload in enumerate(shuffled_payloads):
        result = reassembler.add_fragment(payload)
        if result:
            logger.info(f"Frame Reassembled at packet {i+1}/{len(chunks)}!")
            reassembled_frame = result
            break
            
    # 5. Verify
    assert reassembled_frame is not None, "Failed to reassemble frame!"
    assert len(reassembled_frame) == original_len, "Reassembled size mismatch!"
    
    # Check if opencv can digest the result
    np_arr = np.frombuffer(reassembled_frame, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    assert img is not None, "Reassembled bytes are not a valid image!"
    assert img.shape == (480, 640, 3) or img.shape == (480, 640, 4), f"Image shape mismatch: {img.shape}"
    
    logger.info("Media Pipeline Test PASSED!")

if __name__ == "__main__":
    try:
        test_media_pipeline()
    except Exception as e:
        logger.error(f"Test Failed: {e}")
        exit(1)

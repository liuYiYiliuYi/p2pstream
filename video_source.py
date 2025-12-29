import cv2
import time
import numpy as np
import mss
import logging
from typing import List, Tuple
from video_protocol import ChunkPayload

logger = logging.getLogger(__name__)

class ScreenCapturer:
    def __init__(self, monitor_idx=1, width=640, height=480):
        self.sct = mss.mss()
        try:
            self.monitor = self.sct.monitors[monitor_idx]
        except IndexError:
            logger.warning(f"Monitor {monitor_idx} not found, using primary.")
            self.monitor = self.sct.monitors[1] # usually 1 is the first monitor in mss
        
        # Optionally resize capture to target resolution to save bandwidth
        self.target_res = (width, height)
    
    def capture_frame(self) -> bytes:
        """
        Captures screen, resizes, compresses to JPEG, returns bytes.
        """
        try:
            # Capture
            t0 = time.time()
            sct_img = self.sct.grab(self.monitor)
            # Convert to numpy array (BGRA)
            frame = np.array(sct_img)
            # Drop Alpha channel (BGRA -> BGR)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            # Resize
            frame = cv2.resize(frame, self.target_res)
            
            # Compress to JPG
            # Quality 50 is a good tradeoff for speed/size
            retval, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            
            dt = (time.time() - t0) * 1000
            if dt > 30:
                logger.warning(f"Slow Capture+Encode: {dt:.1f}ms")
            
            if not retval:
                raise RuntimeError("Failed to encode frame to JPEG")
                
            return buffer.tobytes()
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return None

class FrameFragmenter:
    # Target payload size for UDP (accounting for IP/UDP headers + Layer 1 header + Layer 3 header)
    # MTU ~1500. Safe payload ~1000.
    MAX_PAYLOAD_SIZE = 1000

    @staticmethod
    def fragment(frame_id: int, frame_data: bytes) -> List[Tuple[int, bytes]]:
        """
        Splits a frame into chunks.
        Returns a list of (chunk_id, packed_video_payload).
        chunk_id = frame_id * 1000 + frag_index
        """
        total_len = len(frame_data)
        num_frags = (total_len + FrameFragmenter.MAX_PAYLOAD_SIZE - 1) // FrameFragmenter.MAX_PAYLOAD_SIZE
        
        result = []
        for i in range(num_frags):
            start = i * FrameFragmenter.MAX_PAYLOAD_SIZE
            end = min(start + FrameFragmenter.MAX_PAYLOAD_SIZE, total_len)
            chunk_data = frame_data[start:end]
            
            # Create Layer 3 Payload
            payload_obj = ChunkPayload(
                frame_id=frame_id,
                total_frags=num_frags,
                frag_index=i,
                data=chunk_data
            )
            packed_payload = payload_obj.pack()
            
            # Generate Chunk ID for Layer 2
            # Prerequisite: num_frags < 1000 for this simple ID scheme
            if num_frags >= 1000:
                logger.warning("Frame too large! Fragment index overlap risk.")
                
            chunk_id = frame_id * 1000 + i
            result.append((chunk_id, packed_payload))
            
        return result

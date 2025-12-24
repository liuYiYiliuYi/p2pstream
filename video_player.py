import cv2
import numpy as np
import logging
from typing import Dict, Optional, List
from video_protocol import ChunkPayload

logger = logging.getLogger(__name__)

class FrameReassembler:
    def __init__(self):
        # frame_id -> {frag_index: data_bytes}
        self.buffers: Dict[int, Dict[int, bytes]] = {}
        # frame_id -> total_frags (to know when complete)
        self.meta: Dict[int, int] = {}
        
        self.last_completed_frame_id = -1

    def add_fragment(self, payload_bytes: bytes) -> Optional[bytes]:
        """
        Parses payload, adds to buffer.
        If a frame is complete and NEWER than the last returned frame, returns full JPEG bytes.
        Otherwise returns None.
        """
        try:
            chunk = ChunkPayload.unpack(payload_bytes)
            
            # Discard old frames immediately to save memory
            if chunk.frame_id <= self.last_completed_frame_id:
                return None
            
            if chunk.frame_id not in self.buffers:
                self.buffers[chunk.frame_id] = {}
                self.meta[chunk.frame_id] = chunk.total_frags
            
            self.buffers[chunk.frame_id][chunk.frag_index] = chunk.data
            
            # Stats Integration: Buffer Health = number of partially or fully buffered frames
            try:
                from stats_manager import StatsManager
                # Count frames that are complete in buffer (waiting to be returned by caller, 
                # though here we return immediately, so this metric is transient. 
                # Better metric: Queue size in main loop. But let's track 'partial frames' for now)
                StatsManager().update_buffer_health(len(self.buffers))
            except ImportError:
                pass

            # Check for completion
            current_buffer = self.buffers[chunk.frame_id]
            total_frags = self.meta[chunk.frame_id]
            
            if len(current_buffer) == total_frags:
                # Reassemble
                full_data = bytearray()
                for i in range(total_frags):
                    full_data.extend(current_buffer[i])
                
                # Cleanup this frame and older partial frames
                self._cleanup(chunk.frame_id)
                self.last_completed_frame_id = chunk.frame_id
                
                return bytes(full_data)
                
            return None
            
        except Exception as e:
            logger.error(f"Reassembly error: {e}")
            return None

    def _cleanup(self, completed_id: int):
        """
        Remove the completed frame and any stale incomplete frames older than it.
        """
        to_del = [fid for fid in self.buffers if fid <= completed_id]
        for fid in to_del:
            del self.buffers[fid]
            del self.meta[fid]

class VideoRenderer:
    def __init__(self, window_name="P2P Stream"):
        self.window_name = window_name

    def render(self, jpeg_data: bytes):
        """
        Decodes and shows the image.
        """
        if not jpeg_data:
            return
            
        try:
            # Bytes -> Numpy
            np_arr = np.frombuffer(jpeg_data, np.uint8)
            # Decode
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if img is None:
                logger.error("Failed to decode JPEG frame")
                return

            # Show
            # Note: cv2.imshow requires a GUI environment. 
            # In headless environments, this might fail or do nothing.
            cv2.imshow(self.window_name, img)
            cv2.waitKey(1) # 1ms delay to process events
            
        except Exception as e:
            logger.error(f"Render error: {e}")

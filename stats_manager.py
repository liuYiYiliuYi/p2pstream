import time
from typing import Dict, List, Any

class StatsManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StatsManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.upload_bytes = 0
        self.download_bytes = 0
        self.start_time = time.time()
        
        # Recent throughput calculation
        self.last_calc_time = time.time()
        self.last_upload_bytes = 0
        self.last_download_bytes = 0
        self.current_upload_rate = 0.0
        self.current_download_rate = 0.0

        self.active_peers: List[tuple] = []
        self.buffer_health = 0
        self.my_bitmap_summary = ""
        
        # Source tracking for visualization
        self.download_by_source: Dict[str, int] = {} 
        self.recent_downloads: List[tuple] = [] # (timestamp, bytes, source)
        
        # Network Quality
        self.avg_rtt = 0.0

    def add_upload(self, num_bytes: int):
        self.upload_bytes += num_bytes

    def add_download(self, num_bytes: int, source: str = "unknown"):
        self.download_bytes += num_bytes
        if source not in self.download_by_source:
            self.download_by_source[source] = 0
        self.download_by_source[source] += num_bytes
        
        # Add to recent list
        self.recent_downloads.append((time.time(), num_bytes, source))

    def update_peers(self, peers: List[tuple]):
        self.active_peers = peers
        
    def update_network_quality(self, avg_rtt: float):
        self.avg_rtt = avg_rtt

    def update_buffer_health(self, count: int):
        self.buffer_health = count

    def update_bitmap(self, summary: str):
        self.my_bitmap_summary = summary

    def get_stats(self) -> Dict[str, Any]:
        # Calculate rates
        now = time.time()
        
        # Update Rates
        dt = now - self.last_calc_time
        if dt >= 1.0: # Update rate every second roughly
            self.current_upload_rate = (self.upload_bytes - self.last_upload_bytes) / dt
            self.current_download_rate = (self.download_bytes - self.last_download_bytes) / dt
            
            self.last_upload_bytes = self.upload_bytes
            self.last_download_bytes = self.download_bytes
            self.last_calc_time = now

        # Calculate Recent Distribution (Last 10s)
        cutoff = now - 10.0
        # Prune old records (keep list small)
        self.recent_downloads = [x for x in self.recent_downloads if x[0] > cutoff]
        
        recent_dist = {}
        for _, b, src in self.recent_downloads:
            recent_dist[src] = recent_dist.get(src, 0) + b

        return {
            "uptime": int(now - self.start_time),
            "upload_rate": self.current_upload_rate,
            "download_rate": self.current_download_rate,
            "total_upload": self.upload_bytes,
            "total_download": self.download_bytes,
            "active_peers": [f"{p[0]}:{p[1]}" for p in self.active_peers],
            "peer_count": len(self.active_peers),
            "buffer_health": self.buffer_health,
            "bitmap": self.my_bitmap_summary,
            "source_distribution": self.download_by_source,
            "source_distribution_10s": recent_dist,
            "avg_rtt": round(self.avg_rtt, 1)
        }

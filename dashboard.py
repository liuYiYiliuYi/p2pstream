from aiohttp import web
import json
import logging
from stats_manager import StatsManager

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>P2P Streamer Dashboard</title>
    <style>
        body { background-color: #1e1e1e; color: #00ff00; font-family: monospace; padding: 20px; }
        .card { border: 1px solid #333; padding: 15px; margin-bottom: 20px; border-radius: 5px; background: #252526; }
        h1, h2 { color: #00ff00; text-shadow: 0 0 5px #00ff00; }
        .stat-value { font-size: 1.5em; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #444; padding: 8px; text-align: left; }
        th { background-color: #333; }
        #log-area { font-size: 0.8em; color: #aaa; height: 100px; overflow-y: scroll; border: 1px solid #444; padding: 5px; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <h1>SJTU P2P Streamer Node</h1>
    
    <div class="card">
        <h2>Network Stats</h2>
        <div>Upload Rate: <span id="upload_rate" class="stat-value">0</span> KB/s</div>
        <div>Download Rate: <span id="download_rate" class="stat-value">0</span> KB/s</div>
        <div>Total Upload: <span id="total_upload">0</span> MB</div>
        <div>Total Download: <span id="total_download">0</span> MB</div>
    </div>

    <div class="card">
        <h2>P2P Status</h2>
        <div>Uptime: <span id="uptime">0</span> s</div>
        <div>Active Peers: <span id="peer_count">0</span></div>
        <div>Bitmap Summary: <span id="bitmap"></span></div>
        <div>Buffer Health: <span id="buffer_health">0</span> frames</div>
        <h3>Peer List</h3>
        <ul id="peer_list"></ul>
    </div>

    <div class="card">
        <h2>Buffer / Throughput</h2>
        <canvas id="trafficChart" width="400" height="100"></canvas>
    </div>

    <div class="card">
        <h2>Data Source Distribution (Total)</h2>
        <div style="width: 300px; height: 300px;">
            <canvas id="sourceChart"></canvas>
        </div>
    </div>

    <div class="card">
        <h2>Data Source (Last 10s) - Realtime</h2>
        <div style="width: 300px; height: 300px;">
            <canvas id="recentSourceChart"></canvas>
        </div>
    </div>

    <script>
        const ctx = document.getElementById('trafficChart').getContext('2d');
        const trafficChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Download Rate (KB/s)',
                    borderColor: '#00ff00',
                    data: [],
                    fill: false
                }, {
                    label: 'Upload Rate (KB/s)',
                    borderColor: '#00ccff',
                    data: [],
                    fill: false
                }]
            },
            options: {
                scales: {
                    x: { display: false },
                    y: { beginAtZero: true }
                },
                elements: { point: { radius: 0 } }
            }
        });

        const ctxSource = document.getElementById('sourceChart').getContext('2d');
        const sourceChart = new Chart(ctxSource, {
            type: 'pie',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: ['#ff6384', '#36a2eb', '#cc65fe', '#ffce56', '#4bc0c0']
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'right' }
                }
            }
        });

        const ctxRecent = document.getElementById('recentSourceChart').getContext('2d');
        const recentChart = new Chart(ctxRecent, {
            type: 'pie',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: ['#ff6384', '#36a2eb', '#cc65fe', '#ffce56', '#4bc0c0']
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'right' }
                }
            }
        });

        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('uptime').textContent = data.uptime;
                    document.getElementById('upload_rate').textContent = (data.upload_rate / 1024).toFixed(1);
                    document.getElementById('download_rate').textContent = (data.download_rate / 1024).toFixed(1);
                    document.getElementById('total_upload').textContent = (data.total_upload / 1024 / 1024).toFixed(2);
                    document.getElementById('total_download').textContent = (data.total_download / 1024 / 1024).toFixed(2);
                    document.getElementById('peer_count').textContent = data.peer_count;
                    document.getElementById('bitmap').textContent = data.bitmap;
                    document.getElementById('buffer_health').textContent = data.buffer_health;

                    const peerList = document.getElementById('peer_list');
                    peerList.innerHTML = '';
                    data.active_peers.forEach(peer => {
                        const li = document.createElement('li');
                        li.textContent = peer;
                        peerList.appendChild(li);
                    });

                    // Update Traffic Chart
                    if (trafficChart.data.labels.length > 50) {
                        trafficChart.data.labels.shift();
                        trafficChart.data.datasets[0].data.shift();
                        trafficChart.data.datasets[1].data.shift();
                    }
                    const now = new Date().toLocaleTimeString();
                    trafficChart.data.labels.push(now);
                    trafficChart.data.datasets[0].data.push(data.download_rate / 1024);
                    trafficChart.data.datasets[1].data.push(data.upload_rate / 1024);
                    trafficChart.update();

                    // Update Source Chart (Total)
                    if (data.source_distribution) {
                        sourceChart.data.labels = Object.keys(data.source_distribution);
                        sourceChart.data.datasets[0].data = Object.values(data.source_distribution).map(v => (v/1024/1024).toFixed(2));
                        sourceChart.update();
                    }

                    // Update Recent Chart (10s)
                    if (data.source_distribution_10s) {
                        recentChart.data.labels = Object.keys(data.source_distribution_10s);
                        recentChart.data.datasets[0].data = Object.values(data.source_distribution_10s).map(v => (v/1024).toFixed(2));
                        recentChart.update();
                    }
                });
        }

        setInterval(updateStats, 1000);
    </script>
</body>
</html>
"""

async def handle_index(request):
    return web.Response(text=HTML_TEMPLATE, content_type='text/html')

async def handle_stats(request):
    stats = StatsManager().get_stats()
    return web.json_response(stats)

async def start_dashboard(port=8888):
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/stats', handle_stats)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Dashboard started at http://localhost:{port}")
    return site

from aiohttp import web
import json
import logging
from stats_manager import StatsManager

logger = logging.getLogger(__name__)

# ==========================================
# VIEWER DASHBOARD (Local Stats Focus)
# ==========================================
VIEWER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>P2P Viewer Node (Local Stats)</title>
    <style>
        body { background-color: #1e1e1e; color: #00ff00; font-family: monospace; padding: 20px; }
        .card { border: 1px solid #333; padding: 15px; margin-bottom: 20px; border-radius: 5px; background: #252526; }
        h1, h2, h3 { color: #00ff00; text-shadow: 0 0 5px #00ff00; }
        .stat-value { font-size: 1.5em; font-weight: bold; }
        ul { list-style-type: none; padding: 0; }
        li { padding: 5px 0; border-bottom: 1px solid #333; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <h1>P2P Viewer Node</h1>
    
    <div class="card">
        <h2>Local Network Stats</h2>
        <div>Upload Rate: <span id="upload_rate" class="stat-value">0</span> KB/s</div>
        <div>Download Rate: <span id="download_rate" class="stat-value">0</span> KB/s</div>
        <div>Total Upload: <span id="total_upload">0</span> MB</div>
        <div>Total Download: <span id="total_download">0</span> MB</div>
    </div>

    <div class="card">
        <h2>P2P Status</h2>
        <div>Uptime: <span id="uptime">0</span> s</div>
        <div>Active Peers: <span id="peer_count">0</span></div>
        <div>Buffer Health: <span id="buffer_health">0</span> frames</div>
        <div>Avg RTT: <span id="avg_rtt_display">0</span> ms</div>
        <h3>Peer List</h3>
        <ul id="peer_list"></ul>
    </div>

    <div class="card">
        <h2>Buffer / Throughput</h2>
        <canvas id="trafficChart" width="400" height="100"></canvas>
    </div>

    <div class="card">
        <h2>My Source Distribution (Last 10s)</h2>
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
                    label: 'Download (KB/s)',
                    borderColor: '#00ff00',
                    data: [],
                    fill: false
                }, {
                    label: 'Upload (KB/s)',
                    borderColor: '#00ccff',
                    data: [],
                    fill: false
                }]
            },
            options: {
                scales: { x: { display: false }, y: { beginAtZero: true } },
                elements: { point: { radius: 0 } },
                animation: false
            }
        });

        const ctxRecent = document.getElementById('recentSourceChart').getContext('2d');
        const recentChart = new Chart(ctxRecent, {
            type: 'pie',
            data: { labels: [], datasets: [{ data: [], backgroundColor: ['#ff6384', '#36a2eb', '#cc65fe', '#ffce56', '#4bc0c0'] }] },
            options: { responsive: true, plugins: { legend: { position: 'right' } } }
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
                    document.getElementById('buffer_health').textContent = data.buffer_health;
                    document.getElementById('avg_rtt_display').textContent = data.avg_rtt ? data.avg_rtt : 0;

                    const peerList = document.getElementById('peer_list');
                    peerList.innerHTML = '';
                    data.active_peers.forEach(peer => {
                        const li = document.createElement('li');
                        li.textContent = peer;
                        peerList.appendChild(li);
                    });

                    if (trafficChart.data.labels.length > 50) {
                        trafficChart.data.labels.shift();
                        trafficChart.data.datasets[0].data.shift();
                        trafficChart.data.datasets[1].data.shift();
                    }
                    trafficChart.data.labels.push(new Date().toLocaleTimeString());
                    trafficChart.data.datasets[0].data.push(data.download_rate / 1024);
                    trafficChart.data.datasets[1].data.push(data.upload_rate / 1024);
                    trafficChart.update();

                    // Update Recent Chart
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

# ==========================================
# BROADCASTER DASHBOARD (Global Monitor Focus)
# ==========================================
BROADCASTER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Global Network Monitor (Broadcaster)</title>
    <style>
        body { background-color: #000; color: #00ff00; font-family: monospace; padding: 20px; }
        .card { border: 1px solid #444; padding: 15px; margin-bottom: 20px; border-radius: 5px; background: #111; }
        h1 { color: #fff; border-bottom: 1px solid #333; padding-bottom: 10px; }
        h2 { color: #aaa; margin-top: 0; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { border: 1px solid #333; padding: 8px; text-align: left; }
        th { background-color: #222; }
        .metric-big { font-size: 2em; font-weight: bold; color: #fff; }
        .grid-container { display: flex; flex-wrap: wrap; gap: 20px; }
        .peer-card { flex: 0 0 300px; border: 1px solid #333; background: #1a1a1a; padding: 10px; border-radius: 4px; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <h1>GLOBAL NETWORK MONITOR</h1>
    
    <div class="card">
        <h2>Network Summary</h2>
        <div style="display: flex; gap: 40px;">
             <div>
                 <div>Total Nodes Observed</div>
                 <div id="total_nodes" class="metric-big">0</div>
             </div>
             <div>
                 <div>Broadcaster Upload</div>
                 <div class="metric-big"><span id="broadcast_rate">0</span> KB/s</div>
             </div>
             <div>
                 <div>Uptime</div>
                 <div id="uptime" class="metric-big">0s</div>
             </div>
        </div>
    </div>

    <div class="card">
        <h2>Global Topology & Throughput Table</h2>
        <table>
            <thead>
                <tr>
                    <th>Address</th>
                    <th>Role</th>
                    <th>Download (KB/s)</th>
                    <th>Upload (KB/s)</th>
                    <th>Buffer</th>
                    <th>RTT (ms)</th>
                    <th>Sources (Last 10s breakdown)</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody id="global_table_body"></tbody>
        </table>
    </div>

    <div class="card">
        <h2>Global Source Distribution (Stacked View)</h2>
        <div style="height: 300px;">
            <canvas id="globalSourceChart"></canvas>
        </div>
    </div>

    <h2>Peer Detail Cards (Realtime Pie Charts per Peer)</h2>
    <div id="peer_cards_container" class="grid-container">
        <!-- Dynamic Cards -->
    </div>

    <script>
        // --- CHARTS SETUP ---
        const globalSourceChart = new Chart(document.getElementById('globalSourceChart').getContext('2d'), {
            type: 'bar',
            data: { labels: [], datasets: [] },
            options: {
                responsive: true, maintainAspectRatio: false,
                animation: false, // DISABLE ANIMATION for stability
                plugins: { legend: { position: 'top' } },
                scales: { x: { stacked: true }, y: { stacked: true } }
            }
        });

        const colorPalette = ['#36a2eb', '#ff6384', '#cc65fe', '#ffce56', '#4bc0c0', '#9966ff', '#ff9f40', '#e7e9ed', '#71B37C'];
        function getColor(str) {
            let hash = 0;
            for (let i = 0; i < str.length; i++) { hash = str.charCodeAt(i) + ((hash << 5) - hash); }
            return colorPalette[Math.abs(hash) % colorPalette.length];
        }

        const peerChartInstances = {};
        // Keep track of all unique sources we have ever seen to prevent color shifting
        const knownSources = new Set(); 

        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    // 1. Summary
                    document.getElementById('uptime').textContent = data.uptime + 's';
                    document.getElementById('broadcast_rate').textContent = (data.upload_rate / 1024).toFixed(1);

                    // Global Stats Processing
                    const gStats = data.global_stats || {};
                    const peers = Object.keys(gStats).sort();
                    document.getElementById('total_nodes').textContent = peers.length + 1; // +1 for self

                    // 2. Table Update
                    const tableBody = document.getElementById('global_table_body');
                    // ... (keep table logic same, just focusing on chart logic for this replacement block)
                    // Wait, I need to include the table logic if I replace the whole block.
                    // To keep it simple, let's just replace the Chart Update logic part specifically if possible, 
                    // or rewrite the whole function carefully.
                    
                    tableBody.innerHTML = '';
                    peers.forEach(addr => {
                        const s = gStats[addr];
                        const age = (new Date().getTime()/1000 - s.last_seen).toFixed(1);
                        let status = "OK";
                        let color = "#0f0";
                        if(age > 5) { status="LAG"; color="#fa0"; }
                        if(age > 10) { status="LOST"; color="#f00"; }
                        
                        let sourceText = "";
                        if(s.sources) {
                           let total = Object.values(s.sources).reduce((a,b)=>a+b, 0);
                           if(total > 0) {
                               let parts = [];
                               Object.keys(s.sources).forEach(k => {
                                   let pct = Math.round(s.sources[k]/total * 100);
                                   if(pct>1) parts.push(`${k}: ${pct}%`);
                               });
                               sourceText = parts.join(', ');
                           }
                        }

                        const row = `<tr>
                           <td>${addr}</td>
                           <td>${s.role}</td>
                           <td>${(s.dl_rate/1024).toFixed(1)}</td>
                           <td>${(s.ul_rate/1024).toFixed(1)}</td>
                           <td>${s.buffer}</td>
                           <td>${s.rtt.toFixed(0)}</td>
                           <td style="font-size:0.8em; color:#ccc;">${sourceText}</td>
                           <td style="color:${color}">${status} (${age}s ago)</td>
                        </tr>`;
                        tableBody.innerHTML += row;
                    });

                    // 3. Stacked Chart STABILIZED (Object Reuse Mode)
                    // Update known sources
                    peers.forEach(p => {
                        if(gStats[p].sources) Object.keys(gStats[p].sources).forEach(k => knownSources.add(k));
                    });
                    const sourceList = Array.from(knownSources).sort(); 
                    
                    // Update Labels (X-Axis)
                    globalSourceChart.data.labels = peers;
                    
                    // Update Datasets: Sync with sourceList order
                    // We rebuild the datasets array, BUT we try to preserve existing objects if possible?
                    // actually, for stacked charts, order matters.
                    // Let's map sourceList to datasets.
                    
                    const nextDatasets = sourceList.map(src => {
                        // Find existing dataset for this source to reuse color/meta
                        let existing = globalSourceChart.data.datasets.find(d => d.label === src);
                        
                        const newData = peers.map(p => {
                             let val = 0;
                             if(gStats[p].sources && gStats[p].sources[src]) val = gStats[p].sources[src];
                             return val / 1024; // KB
                        });

                        if (existing) {
                            existing.data = newData;
                            return existing;
                        } else {
                            return {
                                label: src,
                                data: newData,
                                backgroundColor: getColor(src)
                            };
                        }
                    });
                    
                    globalSourceChart.data.datasets = nextDatasets;
                    globalSourceChart.update('none'); // ZERO animation update

                    // 4. Peer Cards (Pie Charts)
                    const container = document.getElementById('peer_cards_container');
                    
                    // Cleanup old
                    Object.keys(peerChartInstances).forEach(p => {
                        if(!gStats[p]) {
                            peerChartInstances[p].destroy();
                            delete peerChartInstances[p];
                            const el = document.getElementById('card_' + p.replace(/[^a-zA-Z0-9]/g, '_'));
                            if(el) el.remove();
                        }
                    });

                    peers.forEach(p => {
                        const safeId = 'card_' + p.replace(/[^a-zA-Z0-9]/g, '_');
                        let card = document.getElementById(safeId);
                        if(!card) {
                            card = document.createElement('div');
                            card.className = "peer-card";
                            card.id = safeId;
                            card.innerHTML = `
                                <div style="font-weight:bold; margin-bottom:5px;">${p}</div>
                                <div style="height:200px;"><canvas id="canvas_${safeId}"></canvas></div>
                                <div style="text-align:center; font-size:0.8em; margin-top:5px;">Buf: <span id="buf_${safeId}"></span></div>
                            `;
                            container.appendChild(card);
                            peerChartInstances[p] = new Chart(document.getElementById(`canvas_${safeId}`).getContext('2d'), {
                                type: 'pie',
                                data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
                                options: { maintainAspectRatio: false, plugins: { legend: { display: false } } }
                            });
                        }
                        
                        // Update Card Data
                        document.getElementById(`buf_${safeId}`).textContent = gStats[p].buffer;
                        
                        const srcObj = gStats[p].sources || {};
                        const labels = Object.keys(srcObj);
                        const dataVals = Object.values(srcObj).map(v=>(v/1024).toFixed(2));
                        const colors = labels.map(l => getColor(l));
                        
                        const chart = peerChartInstances[p];
                        chart.data.labels = labels;
                        chart.data.datasets[0].data = dataVals;
                        chart.data.datasets[0].backgroundColor = colors;
                        chart.update();
                    });

                });
        }
        setInterval(updateStats, 1000);
    </script>
</body>
</html>
"""

async def handle_index(request):
    # Determine which template to serve based on Role
    role = StatsManager().role
    if role == "broadcaster":
        return web.Response(text=BROADCASTER_HTML, content_type='text/html')
    else:
        return web.Response(text=VIEWER_HTML, content_type='text/html')

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

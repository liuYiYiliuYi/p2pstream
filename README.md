# SJTU-P2P-Streamer

一个基于 Python asyncio 实现的分布式桌面直播系统。采用分层架构设计，实现了 UDP 传输、P2P 组网、媒体切片与重组，并配备实时 Web 监控面板。

## 架构概览

- **Layer 1 (Transport)**: 异步 UDP 传输与自定义 Packet 协议。
- **Layer 2 (P2P Logic)**: 邻居发现、心跳维护、Bitmap 交换与 Pull-based 数据调度。
- **Layer 3 (Media)**: 屏幕捕获 (mss)、JPEG 编解码 (OpenCV)、帧切片与乱序重组。
- **Layer 4 (App)**: Web 仪表盘监控 (aiohttp) 与主控制逻辑。

## 环境依赖


需要 Python 3.10+。

### 使用 Conda 配置环境 (推荐)

如果您使用 Anaconda 或 Miniconda，建议创建独立环境：

```bash
# 1. 创建名为 p2pstream 的环境，指定 Python 3.10
conda create -n p2pstream python=3.10

# 2. 激活环境
conda activate p2pstream

# 3. 安装依赖
pip install -r requirements.txt
```

或者手动安装：

```bash
pip install opencv-python mss numpy aiohttp
```

## 快速开始

### 1. 启动广播端 (Broadcaster)

作为直播源，捕获屏幕数据并对外分发。

```bash
python3 main.py --role broadcaster --port 8888
```

- **视频窗口**: 会显示一个名为空白的 Dummy 窗口（由于 Mac 兼容性需求）。
- **监控面板**: 打开浏览器访问 [http://localhost:8888](http://localhost:8888)。

### 2. 启动观看端 (Viewer)

加入 P2P 网络，拉取并播放视频。

```bash
# 启动第一个 Viewer，连接到 Broadcaster
python3 main.py --role viewer --port 8889 --connect 127.0.0.1:8888
```

- **视频窗口**: 弹出 "P2P Stream Viewer" 窗口，实时播放画面。
- **监控面板**: 访问 [http://localhost:8889](http://localhost:8889)。

### 3. 多节点扩展

启动更多 Viewer，可以连接到任意已知的节点（Broadcaster 或 其他 Viewer），形成 P2P 网络。

```bash
# Viewer 2 连接到 Viewer 1
python3 main.py --role viewer --port 8889 --connect 127.0.0.1:8889
```

系统会自动交换 Bitmap，Viewer 2 能够从 Viewer 1 处获取数据（如果 Viewer 1 已经缓存了数据），从而减轻 Broadcaster 的压力。

## 监控指标说明

在 Web Dashboard 中可以看到：
- **Upload/Download Rate**: 实时吞吐带宽。
- **Peer Count**: 当前连接的邻居数量。
- **Bitmap Summary**: 当前拥有的数据块范围。
- **Buffer Health**: 视频缓冲区积压的完整帧数。

---
Copyright © 2025 SJTU P2P Group

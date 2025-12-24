# 第四层：应用与监控 UI 层 (App & Dashboard Layer) 设计文档

## 1. 设计目标 (Design Goals)

本层是系统的“大脑”与“面孔”，负责：
1.  **整合**：将 L1 传输、L2 P2P 调度、L3 媒体编解码串联起来。
2.  **可视化**：提供 Web 仪表盘，让难以捉摸的 P2P 内部状态（如带宽、缓冲区、邻居位图）变得可见。
3.  **用户接口**：通过统一的入口 `main.py` 简化启动流程。

## 2. 核心组件 (Core Components)

### 2.1 全局监控 (`StatsManager`)

-   **模式**：单例模式 (Singleton)。任何层级的代码都可以通过 `StatsManager()` 获取实例并汇报数据。
-   **埋点集成**：
    -   **Layer 1**: 每次 `sendto` / `recvfrom` 时累加字节数 -> 计算实时吞吐率 (Bps)。
    -   **Layer 2**: `P2PNode` 定期汇报活跃邻居列表和 Bitmap 状态。
    -   **Layer 3**: `FrameReassembler` 汇报缓冲区健康度（待播放帧数）。

### 2.2 Web 仪表盘 (`Dashboard`)

-   **技术栈**：`aiohttp` (Web Server) + `Chart.js` (前端图表)。
-   **Endpoint**:
    -   `/`: 返回嵌入式 HTML 页面。
    -   `/api/stats`: 返回 JSON 格式的实时监控数据。
-   **刷新机制**：前端 JS 每秒轮询一次 API，动态更新图表和 DOM 元素，实现“秒级”监控。

### 2.3 主程序 (`Main`)

`main.py` 是系统的入口，负责协调多个并发任务：
1.  **事件循环 (Event Loop)**：基于 `asyncio`。
2.  **Broadcaster 逻辑**：
    -   `capture` -> `fragment` -> `store in P2PNode`。
    -   源节点扮演“种子”角色，将数据注入网络。
3.  **Viewer 逻辑**：
    -   `P2PNode` 后台拉取数据 -> `reassemble` -> `render`。
4.  **UI 兼容性**：利用 `asyncio.sleep` 定期释放控制权给 `cv2.waitKey`，防止 OpenCV 窗口在异步环境中卡死。

## 3. 使用方法

请参考根目录下的 `README.md` 获取详细的启动指令。

---
*文档更新日期: 2025-12-24*

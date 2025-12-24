# 第二层：P2P 协议与路由层 (P2P Logic Layer) 设计文档

## 1. 设计目标 (Design Goals)

本层的核心目标是在不可靠的 UDP 传输层之上，构建一个**去中心化的数据分发网络**。
主要功能包括：
1.  **邻居发现与维护**：通过握手和心跳机制维护活跃节点列表。
2.  **数据可用性交换**：通过 Bitmap 机制告知邻居自己拥有哪些数据块。
3.  **拉取式调度 (Pull-based Scheduling)**：主动向拥有数据的邻居发起请求，实现数据的快速扩散。

## 2. 协议扩展 (Protocol Extensions)

在 Layer 1 的通用 Packet 基础上，我们在 `p2p_protocol.py` 中定义了具体的 `msg_type`：

-   **`TYPE_HANDSHAKE` (0x01)**: 新节点加入时发送，建立连接。
-   **`TYPE_HEARTBEAT` (0x02)**: 定期发送（每 2 秒），防止被邻居判定为离线。
-   **`TYPE_BITMAP` (0x03)**: 广播 payload 为 JSON 格式的 Chunk ID 列表 (e.g., `[1, 2, 3]`)，告知邻居“我有这些数据”。
-   **`TYPE_REQUEST` (0x04)**: 向邻居请求特定的 Chunk ID。
-   **`TYPE_DATA` (0x05)**: 响应请求，传输实际的视频数据块。

## 3. 核心组件 (Core Components)

### 3.1 邻居管理 (`PeerManager`)
-   **职责**：维护一张活跃邻居表 `peers: Dict[address, Peer]`.
-   **机制**：
    -   记录每个邻居的 `last_seen` 时间戳。
    -   `prune_dead_peers()`: 定期（每 5 秒）清理超过 5 秒未通信的死亡节点。
    -   `remote_bitmap`: 维护每个邻居拥有的数据视图，作为调度器的决策依据。

### 3.2 P2P 节点逻辑 (`P2PNode`)
-   **职责**：集成 Transport 层，运行核心事件循环。
-   **核心循环 (Background Tasks)**：
    1.  **`loop_heartbeat`**: 给所有已知邻居发心跳。
    2.  **`loop_broadcast_bitmap`**: 每秒广播一次自己的 Bitmap，确保邻居知道我的最新状态。
    3.  **`loop_schedule_fetch` (调度器)**：
        -   计算 `missing_chunks = known_remote_chunks - my_chunks`。
        -   随机选择一个缺失的 chunk。
        -   在拥有该 chunk 的邻居中随机选择一个目标。
        -   发送 `TYPE_REQUEST`。

## 4. 测试与验证 (Verification)

代码位置：`tests/test_layer2.py`

我们模拟了一个最小化的 P2P 网络拓扑：
-   **Node A (Broadcaster)**: 初始拥有数据 `[1, 2, 3]`。
-   **Node B & C (Viewers)**: 初始为空。

**测试流程**与结果：
1.  **握手**：B 和 C 启动并连接 A。
2.  **Bitmap 同步**：A 广播 Bitmap `[1, 2, 3]`，B 和 C 收到了并更新了对 A 的视图。
3.  **数据拉取**：B 和 C 的调度器发现自己缺 1, 2, 3，且 A 有，于是向 A 发起请求。
4.  **数据接收**：A 响应请求发送 TYPE_DATA，B 和 C 收到数据并存入本地 `data_store`。
5.  **最终一致性**：在 **2秒内**，B 和 C 的 Bitmap 均变为 `[1, 2, 3]`，全网数据同步完成。

---
*文档更新日期: 2025-12-24*

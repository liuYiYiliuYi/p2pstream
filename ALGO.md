# P2P 直播算法详细技术文档

本文档基于 `src/core` 下的源代码（特别是 `peer_dbs.py`, `peer_dbs_rarest.py`, `peer_dbs_edf.py`, `splitter_dbs.py`），详细描述了各个算法的内部机制、通信协议和状态管理逻辑。该文档旨在为将仿真算法移植到实际生产环境提供精确指导。


**源码文件**: `src/core/splitter_dbs.py`

Splitter 是直播流的源头，负责接纳新节点并进行初始的数据分发。

### 2.1 初始分发 (Source Seed)
Splitter 使用 **Round-Robin (轮询)** 策略将产生的数据块依次发送给当前在线的 Peers。
*   **逻辑**: 每一个 Peer 只能从源头获得 `1/N` 的数据量。
*   **代码行为**:
    ```python
    # 伪代码
    peer_index = 0
    for chunk in stream:
        target_peer = team[peer_index]
        send_to(target_peer, chunk)
        peer_index = (peer_index + 1) % len(team)
    ```
*   **目的**: 强制 Peer 之间必须互助（Peer 必须找到拥有其他 `(N-1)/N` 数据的邻居）才能完整播放视频。

### 2.2 引导 (Bootstrap)
当新 Peer 连接 Splitter 时：
1.  建立 TCP 连接。
2.  Splitter 发送当前所有在线 Peers 的列表（IP, Port, ID）。
3.  新 Peer 获得这张列表，作为它的初始**邻居列表 (Neighbor List)**。
4.  Splitter 将新 Peer 加入 `team` 列表，开始向其轮询发送数据。

---

## 3. Peer 算法详解

### 3.1 基础算法: Default (Pure Push)
**源码文件**: `src/core/peer_dbs.py`
**模式**: **Source-Push (源驱动推送/泛洪)**

这是最基础的算法，其他高级算法都继承自它。

1.  **邻居管理 (`forward` 表)**:
    *   维护一个 `forward` 字典，`forward[self.public_endpoint]` 存储所有已知的邻居。
    *   当收到 `HELLO` 消息时，将对方加入邻居表。

2.  **推送逻辑 (Push)**:
    *   **触发**: 当 Peer 从 **Splitter** 收到一个 Chunk 时（意味着它是该 Chunk 的源头拥有者之一）。
    *   **行为**: 立即将该 Chunk 放入发送队列，准备发送给**所有**邻居。
    *   **代码机制**:
        *   `update_pendings(origin, chunk_n)`: 遍历所有邻居，将 `chunk_n` 加入每个邻居的 `pending` 队列。
        *   `send_chunks(neighbor)`: 只要 Socket 允许，就从 `pending` 队列取出数据发送 (FIFO)。

3.  **被动性**:
    *   Default 算法**不主动请求 (No Pull)**。如果网络丢包或拓扑断裂，它不会修复，只会丢失数据。它完全依赖 Splitter 的 RR 分发和 Peer 间的泛洪。

---

### 3.2 进阶算法: Rarest First (最稀缺优先)
**源码文件**: `src/core/peer_dbs_rarest.py`
**模式**: **Hybrid (Push + Pull)**

在 Default 的 Push 基础上，增加了主动 Pull 机制，专门请求网络中“最稀少”的块，以提高数据可用性。

1.  **可用性感知 (Buffer Map)**:
    *   **广播**: Peer 周期性（或收到新块时）向邻居发送 `BUFFER_MAP_MSG`，告知自己有哪些块。
    *   **记录**: 维护 `neighbor_buffer_maps`，记录每个邻居拥有的块。
    *   **稀缺度计算**:
        ```python
        availability(chunk_k) = sum(1 for neighbor in neighbors if neighbor.has(chunk_k))
        ```
        值越小越稀缺。

2.  **Pull 策略 (Request Logic)**:
    *   **调度窗口**: 检查播放指针未来 `K` 个块（例如 16 个）。
    *   **选择**: 在所有**缺失**且**邻居拥有**的块中，选择 `availability` 最低（最稀缺）的一个。
    *   **发送请求**: 向拥有该块的随机邻居发送 `REQUEST_RAREST_MSG`。

3.  **双队列与去重 (Double Queue & Dedup)**:
    *   **两个队列**:
        *   `pending_pull`: 存放别人请求我要的数据（高优先级）。
        *   `pending`: 存放我要 Push 给别人的数据（低优先级）。
    *   **发送优先级**: 每次尝试发送时，**优先清空 `pending_pull`**，然后再发送 `pending`。
    *   **去重 (Critical)**:
        *   当 Peer 收到一个针对 Chunk X 的 PULL 请求时，它会立即检查自己的 PUSH 队列。如果 Chunk X 正好在 PUSH 队列里等着发给这个人，它会**从 PUSH 队列中删除 X**，然后通过高优先级的 PULL 响应通道发送。这避免了重复发送两次相同的数据。

---

### 3.3 进阶算法: EDF (最早截止时间优先)
**源码文件**: `src/core/peer_dbs_edf.py`
**模式**: **Hybrid (Push + Pull)**

目标是最小化播放卡顿，优先抢救马上要播放的数据。

1.  **状态交换**:
    *   除了 `BUFFER_MAP`，还交换 `PLAYBACK_POS`（播放进度）。
    *   这让邻居知道你急需什么。

2.  **Pull 策略**:
    *   **紧迫度**: 总是请求 `chunk_to_play` 之后**第一个**缺失的块。
    *   **逻辑**:
        ```python
        for i in range(window):
            chunk = chunk_to_play + i
            if (I_dont_have(chunk) and Neighbor_has(chunk)):
                Request(chunk)
                break # 只请求最急的一个
        ```
    *   不考虑稀缺度，只考虑截止时间 (Deadline)。

3.  **优先级**:
    *   与 Rarest 类似，PULL 响应优先级高于 PUSH。

---


# 第一层：网络传输层 (Network Transport Layer) 设计文档

## 1. 设计目标 (Design Goals)

本层的核心目标是为上层提供一个**低延迟**、**高吞吐**且能**容忍丢包**的基础通信服务。考虑到直播场景对实时性的极高要求，我们选择了 **UDP** 作为传输协议，而不是 TCP。TCP 的重传机制和拥塞控制虽然保证了可靠性，但在弱网环境下会导致不可接受的延迟（Head-of-Line Blocking）。

本层主要负责：
1.  **数据的序列化与反序列化**：定义统一的数据包格式。
2.  **异步 UDP 传输**：利用 Python `asyncio` 实现非阻塞的高性能 I/O。
3.  **基础元数据封装**：在包头中包含序号、时间戳等信息，为上层（Layer 2）实现丢包检测、乱序重排和 RTT 计算提供支持。

## 2. 协议设计 (Protocol Design)

我们设计了一个紧凑的二进制协议头部，使用 Python 的 `struct` 模块进行处理。

### Packet 结构

```python
@dataclass
class Packet:
    ver: int          # 版本号 (1 byte)
    msg_type: int     # 消息类型 (1 byte)
    seq: int          # 序列号 (4 bytes, unsigned int)
    timestamp: float  # 时间戳 (8 bytes, double)
    payload: bytes    # 负载数据
```

- **Header Format**: `!BBIdH` (Network Byte Order / Big Endian)
    - `B`: Version
    - `B`: Type
    - `I`: Sequence Number
    - `d`: Timestamp
    - `H`: Payload Length (2 bytes, unsigned short)

**设计考量**：
- **`seq`**: 4字节整数足以支持长时间的传输而不溢出（回绕处理由上层逻辑负责）。
- **`timestamp`**: 使用双精度浮点数记录发送时间，接收端收到后可直接 `current_time - packet.timestamp` 计算单向延迟（需时钟同步）或用于 RTT 估算。
- **`payload_len`**: 显式记录负载长度，用于完整性校验。如果接收到的 UDP 包总长度不等于 `HeaderSize + payload_len`，则视为畸形包丢弃。

## 3. 传输实现 (Transport Implementation)

代码位置：`transport.py`

我们使用 Python 标准库 `asyncio` 的 `create_datagram_endpoint` 来管理 UDP Socket。

### 关键组件

1.  **`UDPTransport` 类**：
    - 封装了底层的 asyncio Protocol 操作。
    - **发送**：`send_packet` 方法将 Packet 对象序列化为 bytes 直接发送。
    - **接收**：通过 `on_packet_received` 回调函数将解析好的 Packet 对象传递给业务层。这种回调机制实现了 Layer 1 与 Layer 2 的解耦。

2.  **异常处理**：
    - 在接收路径上（`datagram_received`），任何解析错误（如魔数不对、校验和失败、长度非法）都会被捕获并记录日志，防止单个坏包导致服务崩溃。

## 4. 测试与验证 (Verification)

代码位置：`tests/test_layer1.py`

为了验证传输层的健壮性，我们编写了一个集成测试脚本，模拟了真实的弱网环境：

- **模拟丢包 (Packet Loss)**：以 10% 的概率随机丢弃接收到的数据包。
- **模拟延迟 (Latency/Jitter)**：对接收到的数据包增加 0-50ms 的随机延迟。

**测试结果验证**：
- 发送方连续发送 100 个包。
- 接收方统计收到的包序号。
- 最终验证收到的包数量符合预期的丢包率范围，且程序能够正确处理乱序到达的包（尽管 Layer 1 本身不排序，但测试代码验证了数据完整性）。

---
*文档更新日期: 2025-12-24*

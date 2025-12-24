# 第三层：媒体编解码层 (Media Layer) 设计文档

## 1. 设计目标 (Design Goals)

本层负责将连续的**桌面画面**转化为适合 P2P 网络传输的**离散数据块 (Chunks)**，并在接收端还原播放。
核心挑战在于：
1.  **大帧切片 (Fragmentation)**：单帧画面（JPEG 压缩后约 30KB - 100KB）远超 UDP MTU (1500 bytes)，必须切片。
2.  **乱序重组 (Reassembly)**：网络传输会导致切片乱序到达，接收端需要缓存并重新排序。
3.  **实时性**：必须尽可能降低编解码和重组带来的延迟。

## 2. 视频协议 (Video Protocol)

为了支持切片和重组，我们在 UDP/P2P 协议的 payload 内部定义了应用层的 **Chunk Payload** 结构。

代码位置：`video_protocol.py`

### Chunk Payload Structure

```python
@dataclass
class ChunkPayload:
    frame_id: int      # 帧 ID (4 bytes) - 标识属于哪一帧画面
    total_frags: int   # 总切片数 (2 bytes) - 用于判断帧是否完整
    frag_index: int    # 切片索引 (2 bytes) - 标识当前是第几块
    data: bytes        # 实际 JPEG 数据片段
```

-   **Header Format**: `!IHH` (8 bytes total)
-   **切片大小限制**: 我们设定 `MAX_PAYLOAD_SIZE = 1000` 字节。这预留了充足的空间给 Layer 3 Header (8B) + Layer 1 Header (16B) + IP/UDP Headers，避免 IP 分片。

## 3. 核心组件 (Core Components)

### 3.1 视频源端 (`video_source.py`)

1.  **`ScreenCapturer`**:
    -   利用 `mss` 库进行跨平台的屏幕截图。
    -   利用 `opencv` (`cv2.imencode`) 将 Raw 像素压缩为 JPEG 格式。
    -   *优化*：我们设置了 JPEG Quality = 50，并在编码前 resize 到 640x480，以平衡画质与带宽（单帧约 30KB）。

2.  **`FrameFragmenter`**:
    -   输入完整的 JPEG bytes。
    -   计算需要的切片数量 `total_frags`。
    -   生成带有 Header 的二进制包，并分配 P2P 层所需的唯一 `chunk_id` (`frame_id * 1000 + frag_index`)。

### 3.2 视频播放端 (`video_player.py`)

1.  **`FrameReassembler`**:
    -   维护 `buffers: Dict[frame_id, Dict[frag_index, bytes]]`。
    -   当收到切片时：
        1.  若该帧 ID 小于等于“已播放帧 ID”，视为过时数据直接丢弃。
        2.  否则存入 buffer。
        3.  检查是否集齐所有 `total_frags`。
    -   若集齐：拼接所有 bytes，返回完整帧，并清理旧缓存。

2.  **`VideoRenderer`**:
    -   利用 `cv2.imdecode` 解码 JPEG。
    -   利用 `cv2.imshow` 显示画面。

## 4. 测试与验证 (Verification)

代码位置：`tests/test_layer3.py`

我们编写了一个**本地闭环测试**，不依赖网络层，专注于验证媒体流水线的正确性：
1.  **Capture**: 截取当前屏幕，得到约 28KB 的数据。
2.  **Fragment**: 切割成 29 个小块。
3.  **Shuffle (关键)**：随机打乱这 29 个块的顺序，模拟极其不稳定的网络传输（乱序到达）。
4.  **Reassemble**: 将打乱的块依次喂给重组器。
5.  **Verify**: 重组器成功还原出完整的 JPEG 数据，且经检测是有效的图像。

**结论**：Layer 3 的切片重组逻辑具备处理乱序数据包的能力，且编解码流程畅通。

---
*文档更新日期: 2025-12-24*

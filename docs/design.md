# 运动相机视频压缩工具 — 设计方案

## 1. 项目背景

运动相机（GoPro、DJI Action、Insta360 等）拍摄的视频码率极高，通常是感知质量所需的 2~5 倍。一天的拍摄（滑雪、潜水、骑行等）轻松产生 100~300 GB 素材，对存储和传输造成巨大压力。

本工具的目标：**在几乎不损失视觉质量的前提下，将文件体积压缩到原始的 1/3 ~ 1/5**。

### 运动相机视频的典型参数

| 分辨率 | 帧率 | 编码 | 源码率 | 1 分钟文件大小 |
|--------|------|------|--------|----------------|
| 5.3K | 60fps | HEVC | ~120 Mbps | ~900 MB |
| 4K | 60fps | HEVC | 80-100 Mbps | 600-750 MB |
| 4K | 30fps | HEVC | 60-80 Mbps | 400-500 MB |
| 2.7K | 60fps | HEVC | ~60 Mbps | ~450 MB |
| 1080p | 60fps | HEVC | 40-45 Mbps | 250-300 MB |
| 1080p | 30fps | HEVC | 25-30 Mbps | 150-200 MB |

---

## 2. 技术选型

### 2.1 核心引擎：FFmpeg

FFmpeg 是视频处理领域事实上的标准，无可替代。理由：

- 支持所有主流编解码器（H.264 / H.265 / AV1）
- 支持 macOS VideoToolbox 硬件加速
- 成熟稳定，社区活跃
- 命令行友好，易于集成

### 2.2 开发语言：Python

| 方案 | 优势 | 劣势 |
|------|------|------|
| **Python** | 开发快、生态丰富、易维护 | 需要运行时 |
| Swift | 原生 macOS 体验 | 开发周期长 |
| Rust | 单二进制分发、极致性能 | 学习成本高 |

**选择 Python 的理由**：开发效率最高，`typer` + `rich` 提供优秀的 CLI 体验，subprocess 调用 FFmpeg 即可满足所有需求。后期如需 GUI 可用 PyQt/PySide 扩展。

### 2.3 编码策略：VideoToolbox 硬件加速优先

| 对比项 | VideoToolbox（硬件） | libx265（软件） |
|--------|---------------------|-----------------|
| 编码速度 | 5~15x 更快 | 基准 |
| 压缩效率 | 略低 15~25% | 最优 |
| CPU 占用 | 极低（专用芯片） | 极高（全核） |
| 批量处理 | 非常适合 | 适合单文件精调 |

**默认使用 `hevc_videotoolbox` 硬件编码**，Apple Silicon 上质量已相当好。提供 `--software` 选项回退到 `libx265` 软件编码以获取最佳压缩效率。

---

## 3. 压缩参数方案

### 3.1 质量档位

提供三个预设档位，用户也可自定义：

| 档位 | 描述 | VideoToolbox `-q:v` | libx265 CRF | 预期压缩比 |
|------|------|---------------------|-------------|------------|
| **high** | 高质量 — 几乎无损 | 65 | 24 | 2~3x |
| **balanced**（默认） | 均衡 — 推荐日常使用 | 58 | 27 | 3~5x |
| **small** | 最小体积 — 适合分享 | 48 | 30 | 5~8x |

### 3.2 各分辨率目标码率参考（balanced 档位，H.265 输出）

| 分辨率 / 帧率 | 目标码率 | 对比源文件压缩比 |
|---------------|----------|------------------|
| 4K 60fps | 20-28 Mbps | 3~5x |
| 4K 30fps | 15-20 Mbps | 3~4x |
| 2.7K 60fps | 14-18 Mbps | 3~4x |
| 2.7K 30fps | 10-14 Mbps | 3~5x |
| 1080p 60fps | 8-12 Mbps | 3~4x |
| 1080p 30fps | 6-8 Mbps | 3~5x |

> 注：实际使用 CRF / `-q:v` 质量模式编码，码率会根据画面复杂度自适应，上表仅作参考。

### 3.3 核心 FFmpeg 命令

```bash
ffmpeg -hwaccel videotoolbox -i input.mp4 \
  -c:v hevc_videotoolbox \
  -q:v 58 \
  -tag:v hvc1 \
  -c:a copy \
  -map_metadata 0 \
  -movflags +faststart \
  output.mp4
```

关键参数说明：

| 参数 | 作用 |
|------|------|
| `-hwaccel videotoolbox` | 硬件加速解码 |
| `-c:v hevc_videotoolbox` | 硬件加速 H.265 编码 |
| `-q:v 58` | 质量控制（1-100，越高越好） |
| `-tag:v hvc1` | 确保 Apple 设备 / QuickTime 兼容 |
| `-c:a copy` | 音频直接复制，不重编码 |
| `-map_metadata 0` | 保留源文件所有元数据（GPS、时间戳等） |
| `-movflags +faststart` | 将 moov atom 前移，支持快速播放 |

---

## 4. 功能设计

### 4.1 核心功能

1. **智能检测**：自动通过 FFprobe 获取源视频参数（分辨率、编码、码率、帧率），自动选择最优压缩参数
2. **批量处理**：支持目录扫描，递归处理所有视频文件
3. **进度显示**：解析 FFmpeg 输出，实时显示压缩进度条、预计剩余时间
4. **压缩报告**：完成后显示原始大小 / 压缩后大小 / 压缩比 / 节省空间
5. **元数据保留**：GPS、拍摄时间、相机型号等全部保留
6. **安全机制**：默认输出到新目录，不覆盖原始文件

### 4.2 CLI 接口设计

```bash
# 压缩单个文件（默认 balanced 档位）
compress video.mp4

# 压缩整个目录
compress ./GoPro/

# 指定质量档位
compress video.mp4 --quality high
compress video.mp4 --quality small

# 使用软件编码（最佳压缩效率）
compress video.mp4 --software

# 指定输出目录
compress ./GoPro/ --output ./compressed/

# 预览模式（不实际压缩，仅显示预计效果）
compress ./GoPro/ --dry-run

# 并行处理
compress ./GoPro/ --parallel 3
```

### 4.3 智能跳过

- 如果源视频码率已低于目标码率，自动跳过（避免越压越大）
- 如果输出文件已存在且较新，跳过（支持断点续压）

---

## 5. 项目结构

```
action_video_compress/
├── src/
│   └── compress/
│       ├── __init__.py
│       ├── cli.py          # CLI 入口，参数解析（typer）
│       ├── probe.py        # FFprobe 封装：检测分辨率、编码、码率、帧率
│       ├── profiles.py     # 压缩预设档位定义
│       ├── encoder.py      # FFmpeg 命令构建与执行
│       ├── queue.py        # 批量处理队列，支持并行
│       ├── progress.py     # 进度条（rich）
│       └── report.py       # 压缩报告生成
├── tests/
│   ├── test_probe.py
│   ├── test_profiles.py
│   └── test_encoder.py
├── pyproject.toml          # 项目配置、依赖管理
└── docs/
    └── design.md           # 本文档
```

### 依赖

| 包 | 用途 |
|----|------|
| `typer` | CLI 框架 |
| `rich` | 终端美化、进度条、表格 |

外部依赖：`ffmpeg`、`ffprobe`（通过 Homebrew 安装：`brew install ffmpeg`）

---

## 6. 开发计划

### Phase 1 — 核心功能（MVP）

1. FFprobe 封装：读取视频元信息
2. 压缩预设档位定义
3. FFmpeg 命令构建与执行
4. 单文件压缩 + 进度显示
5. 压缩报告

### Phase 2 — 批量与体验

6. 目录扫描 + 批量处理
7. 并行编码支持
8. 智能跳过逻辑
9. dry-run 预览模式

### Phase 3 — 扩展（可选）

10. GUI 界面（PyQt / SwiftUI）
11. GoPro 分段文件自动拼接
12. 自定义 FFmpeg 参数透传
13. 视频缩略图预览

---

## 7. 关键设计决策总结

| 决策 | 选择 | 理由 |
|------|------|------|
| 输出编码 | H.265 (HEVC) | 压缩效率最优，运动相机已普遍使用 |
| 默认编码器 | `hevc_videotoolbox` | Apple Silicon 硬件加速，速度快 5~15x |
| 质量控制 | `-q:v`（硬件）/ CRF（软件） | 自适应码率，比固定码率更智能 |
| 音频处理 | 直接复制不重编码 | 音频仅占 1~2%，重编码无意义 |
| 元数据 | 全部保留 | GPS / 时间戳对运动视频很重要 |
| 原始文件 | 不修改不删除 | 安全第一 |

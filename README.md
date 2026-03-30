# Action Video Compress

Batch video compression tool for action cameras (GoPro, DJI Action, Insta360, etc.).
Auto-detects GPU hardware encoders to compress videos to **1/3 ~ 1/5** of original size with nearly no visible quality loss.

运动相机视频批量压缩工具。自动检测硬件编码器并利用 GPU 加速，在几乎不损失画质的前提下将视频体积压缩到原始的 1/3 ~ 1/5。

## Features

- **Cross-platform** — macOS, Windows, Linux
- **Hardware accelerated** — Auto-detects GPU encoder (VideoToolbox / NVENC / QSV / AMF / VAAPI), 5~15x faster than software encoding
- **Smart detection** — Reads resolution, codec, bitrate, frame rate and picks optimal compression params
- **Metadata preserved** — GPS, timestamps, camera model all retained
- **Resume-friendly** — Skips already-compressed files, supports interrupted batch jobs
- **Safe** — Outputs to a separate directory, never modifies or deletes originals
- **Compression report** — Shows per-file ratio and total space saved

## Supported Hardware Encoders

| Platform | Encoder | Devices |
|----------|---------|---------|
| macOS | `hevc_videotoolbox` | Apple Silicon / Intel Mac |
| Windows / Linux | `hevc_nvenc` | NVIDIA GPU |
| Windows / Linux | `hevc_qsv` | Intel (iGPU) |
| Windows | `hevc_amf` | AMD GPU |
| Linux | `hevc_vaapi` | Intel / AMD GPU |

Falls back to `libx265` software encoding if no hardware encoder is detected.

## Install

**1. Install FFmpeg**

```bash
# macOS
brew install ffmpeg

# Windows
winget install FFmpeg

# Linux (Debian/Ubuntu)
sudo apt install ffmpeg
```

**2. Install this tool**

```bash
pip install -e .
```

## Usage

```bash
# Compress a single file
compress video.mp4

# Compress an entire directory
compress ./GoPro/

# Specify output directory
compress ./GoPro/ -o ./output/

# Dry-run (preview only, no actual compression)
compress ./GoPro/ --dry-run
```

### Quality Presets

Use `-q` to select:

| Preset | Description | Expected Ratio |
|--------|-------------|----------------|
| `high` | High quality, near-lossless | 2~3x |
| `balanced` | **Default**, recommended for daily use | 3~5x |
| `small` | Smallest size, good for sharing | 5~8x |

```bash
compress video.mp4 -q high
compress video.mp4 -q small
```

### Parallel Processing

```bash
compress ./GoPro/ -p 3    # up to 3 concurrent jobs
```

### Software Encoding

Force `libx265` for best compression efficiency (slower):

```bash
compress video.mp4 --software
```

### All Options

```
compress [OPTIONS] INPUT_PATH

Arguments:
  INPUT_PATH                         Video file or directory

Options:
  -o, --output PATH                  Output directory (default: compressed/ next to input)
  -q, --quality [high|balanced|small] Quality preset (default: balanced)
  -s, --software                     Use libx265 software encoding
  -p, --parallel INTEGER             Parallel jobs, 1-8 (default: 1)
  --dry-run                          Preview mode, no actual compression
  --help                             Show help
```

## Supported Formats

**Input:** `.mp4` `.mov` `.avi` `.mkv` `.m4v` `.mts` `.ts`

**Output:** H.265 (HEVC) MP4

## License

MIT

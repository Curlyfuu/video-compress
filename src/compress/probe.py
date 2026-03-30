"""FFprobe 封装：获取视频元信息"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoInfo:
    """视频元信息"""

    path: Path
    width: int
    height: int
    codec: str
    bitrate: int  # bps
    fps: float
    duration: float  # 秒
    size: int  # 字节
    audio_codec: str | None = None

    @property
    def resolution_label(self) -> str:
        if self.height >= 2988:
            return "5.3K"
        if self.height >= 2160:
            return "4K"
        if self.height >= 1520:
            return "2.7K"
        if self.height >= 1080:
            return "1080p"
        if self.height >= 720:
            return "720p"
        return f"{self.height}p"

    @property
    def fps_label(self) -> str:
        r = round(self.fps)
        return f"{r}fps"

    @property
    def bitrate_mbps(self) -> float:
        return self.bitrate / 1_000_000

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)

    @property
    def summary(self) -> str:
        return (
            f"{self.resolution_label} {self.fps_label} "
            f"{self.codec} {self.bitrate_mbps:.1f}Mbps"
        )


def check_ffprobe() -> str:
    """检查 ffprobe 是否可用，返回路径"""
    path = shutil.which("ffprobe")
    if path is None:
        raise FileNotFoundError(
            "未找到 ffprobe，请先安装 FFmpeg：brew install ffmpeg"
        )
    return path


def probe(file: Path) -> VideoInfo:
    """读取视频文件的元信息"""
    ffprobe = check_ffprobe()

    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # 查找视频流
    video_stream = None
    audio_stream = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and video_stream is None:
            video_stream = s
        elif s.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = s

    if video_stream is None:
        raise ValueError(f"未找到视频流：{file}")

    fmt = data.get("format", {})

    # 解析帧率
    fps_str = video_stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 30.0
    else:
        fps = float(fps_str)

    # 解析码率：优先从视频流获取，其次从 format 获取
    bitrate = int(video_stream.get("bit_rate", 0))
    if bitrate == 0:
        total_bitrate = int(fmt.get("bit_rate", 0))
        audio_bitrate = int(audio_stream.get("bit_rate", 0)) if audio_stream else 0
        bitrate = total_bitrate - audio_bitrate if total_bitrate > audio_bitrate else total_bitrate

    return VideoInfo(
        path=file,
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        codec=video_stream.get("codec_name", "unknown"),
        bitrate=bitrate,
        fps=fps,
        duration=float(fmt.get("duration", 0)),
        size=file.stat().st_size,
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
    )

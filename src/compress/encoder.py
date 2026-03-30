"""FFmpeg 命令构建与执行"""

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .probe import VideoInfo
from .profiles import Profile


@dataclass
class EncodeResult:
    """编码结果"""

    input_path: Path
    output_path: Path
    input_size: int
    output_size: int
    success: bool
    error: str | None = None

    @property
    def ratio(self) -> float:
        if self.output_size == 0:
            return 0
        return self.input_size / self.output_size

    @property
    def saved_bytes(self) -> int:
        return self.input_size - self.output_size

    @property
    def saved_percent(self) -> float:
        if self.input_size == 0:
            return 0
        return (self.saved_bytes / self.input_size) * 100


# ---------------------------------------------------------------------------
# 硬件编码器定义（按优先级排列）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HWEncoder:
    """硬件编码器配置"""

    name: str           # FFmpeg 编码器名称
    label: str          # 显示名称
    hwaccel: str | None # -hwaccel 参数（None 表示不需要）
    quality_flag: str   # 质量控制参数名
    quality_map: str    # 质量映射方案标识
    max_sessions: int   # 最大并发会话数


# 各平台硬件编码器，按优先级排列
_HW_ENCODERS = [
    # macOS — VideoToolbox
    HWEncoder(
        name="hevc_videotoolbox",
        label="VideoToolbox (macOS 硬件)",
        hwaccel="videotoolbox",
        quality_flag="-q:v",
        quality_map="vtb",
        max_sessions=3,
    ),
    # NVIDIA GPU — NVENC
    HWEncoder(
        name="hevc_nvenc",
        label="NVENC (NVIDIA 硬件)",
        hwaccel="cuda",
        quality_flag="-cq",
        quality_map="nvenc",
        max_sessions=3,
    ),
    # Intel — Quick Sync Video
    HWEncoder(
        name="hevc_qsv",
        label="QSV (Intel 硬件)",
        hwaccel="qsv",
        quality_flag="-global_quality",
        quality_map="qsv",
        max_sessions=2,
    ),
    # AMD — AMF (Windows) / VAAPI (Linux)
    HWEncoder(
        name="hevc_amf",
        label="AMF (AMD 硬件)",
        hwaccel=None,
        quality_flag="-quality",
        quality_map="amf",
        max_sessions=2,
    ),
    HWEncoder(
        name="hevc_vaapi",
        label="VAAPI (Linux 硬件)",
        hwaccel="vaapi",
        quality_flag="-qp",
        quality_map="vaapi",
        max_sessions=2,
    ),
]


def _get_hw_quality_value(encoder: HWEncoder, profile: Profile) -> str:
    """将统一的 hw_quality (1-100, 越高越好) 映射到各编码器的实际参数值"""
    q = profile.hw_quality  # 1-100, 越高越好

    if encoder.quality_map == "vtb":
        # VideoToolbox: -q:v 1-100, 越高越好（直接使用）
        return str(q)

    if encoder.quality_map == "nvenc":
        # NVENC: -cq 0-51, 越低越好。映射: 100->15, 65->20, 58->22, 48->25
        cq = int(51 - (q / 100) * 36)
        return str(max(0, min(51, cq)))

    if encoder.quality_map == "qsv":
        # QSV: -global_quality 1-51, 越低越好
        gq = int(51 - (q / 100) * 36)
        return str(max(1, min(51, gq)))

    if encoder.quality_map == "amf":
        # AMF: -quality 与 -rc cqp -qp_i / -qp_p 配合，这里用 quality preset
        # 0=speed, 1=balanced, 2=quality
        if q >= 60:
            return "quality"
        if q >= 45:
            return "balanced"
        return "speed"

    if encoder.quality_map == "vaapi":
        # VAAPI: -qp 0-51, 越低越好
        qp = int(51 - (q / 100) * 36)
        return str(max(0, min(51, qp)))

    return str(q)


def check_ffmpeg() -> str:
    """检查 ffmpeg 是否可用，返回路径"""
    path = shutil.which("ffmpeg")
    if path is None:
        system = platform.system()
        if system == "Darwin":
            hint = "brew install ffmpeg"
        elif system == "Windows":
            hint = "winget install FFmpeg 或从 https://ffmpeg.org/download.html 下载"
        else:
            hint = "sudo apt install ffmpeg  或  sudo dnf install ffmpeg"
        raise FileNotFoundError(f"未找到 ffmpeg，请先安装：{hint}")
    return path


def has_encoder(name: str) -> bool:
    """检查 FFmpeg 是否支持指定编码器"""
    ffmpeg = check_ffmpeg()
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True,
        )
        return name in result.stdout
    except Exception:
        return False


@lru_cache(maxsize=1)
def detect_hw_encoder() -> HWEncoder | None:
    """自动检测当前系统可用的最优硬件编码器"""
    for enc in _HW_ENCODERS:
        if has_encoder(enc.name):
            return enc
    return None


def get_encoder_label(software: bool) -> str:
    """获取当前编码器的显示名称"""
    if software:
        return "libx265 (软件)"
    hw = detect_hw_encoder()
    if hw:
        return hw.label
    return "libx265 (软件)"


def get_max_parallel(software: bool) -> int:
    """获取当前编码器建议的最大并发数

    硬件编码器有物理会话数限制，超出后会排队或报错。
    软件编码受 CPU 核心数约束，并行实例过多会互相抢占导致整体变慢。
    """
    import os

    if software:
        # libx265 每个实例会用多核，并行太多反而互抢 CPU
        # 经验值：核心数 / 4，至少 1，最多 4
        cores = os.cpu_count() or 4
        return max(1, min(4, cores // 4))

    hw = detect_hw_encoder()
    if hw:
        return hw.max_sessions

    # 回退到软件编码的限制
    cores = os.cpu_count() or 4
    return max(1, min(4, cores // 4))


def build_command(
    info: VideoInfo,
    profile: Profile,
    output: Path,
    *,
    software: bool = False,
) -> list[str]:
    """构建 FFmpeg 编码命令"""
    ffmpeg = check_ffmpeg()

    cmd = [ffmpeg, "-y", "-hide_banner"]

    if software:
        cmd += ["-i", str(info.path)]
        cmd += [
            "-c:v", "libx265",
            "-crf", str(profile.sw_crf),
            "-preset", "medium",
            "-tag:v", "hvc1",
        ]
    else:
        hw = detect_hw_encoder()
        if hw is None:
            # 回退到软件编码
            cmd += ["-i", str(info.path)]
            cmd += [
                "-c:v", "libx265",
                "-crf", str(profile.sw_crf),
                "-preset", "medium",
                "-tag:v", "hvc1",
            ]
        else:
            # 硬件编码：只加速编码，解码用软件（兼容性更好）
            # -hwaccel 硬件解码对很多运动相机的 H.264 流不兼容，
            # 而软件解码在 Apple Silicon 上依然很快
            cmd += ["-i", str(info.path)]

            quality_val = _get_hw_quality_value(hw, profile)

            if hw.quality_map == "amf":
                cmd += [
                    "-c:v", hw.name,
                    "-quality", quality_val,
                    "-tag:v", "hvc1",
                ]
            elif hw.quality_map == "nvenc":
                cmd += [
                    "-c:v", hw.name,
                    "-rc", "vbr",
                    hw.quality_flag, quality_val,
                    "-tag:v", "hvc1",
                ]
            else:
                cmd += [
                    "-c:v", hw.name,
                    hw.quality_flag, quality_val,
                    "-tag:v", "hvc1",
                ]

    cmd += [
        "-c:a", "copy",
        "-map_metadata", "0",
        "-movflags", "+faststart",
        str(output),
    ]

    return cmd


# 匹配 FFmpeg 进度输出中的 time= 字段
_TIME_PATTERN = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")


def parse_progress_time(line: str) -> float | None:
    """从 FFmpeg 输出行解析当前编码时间（秒）"""
    m = _TIME_PATTERN.search(line)
    if m:
        h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600 + mi * 60 + s + cs / 100
    return None


def encode(
    info: VideoInfo,
    profile: Profile,
    output: Path,
    *,
    software: bool = False,
    on_progress: "callable | None" = None,
) -> EncodeResult:
    """执行编码

    Args:
        info: 源视频信息
        profile: 压缩档位
        output: 输出文件路径
        software: 是否使用软件编码
        on_progress: 进度回调 (current_seconds, total_seconds)
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(info, profile, output, software=software)

    try:
        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
        )

        # 保留最后几行 stderr 用于错误报告
        from collections import deque
        recent_lines = deque(maxlen=5)

        for line in iter(process.stderr.readline, ""):
            recent_lines.append(line.rstrip())
            if on_progress and info.duration > 0:
                current = parse_progress_time(line)
                if current is not None:
                    on_progress(current, info.duration)

        process.wait()

        if process.returncode != 0:
            # 从 stderr 中提取有意义的错误信息
            error_lines = [l for l in recent_lines if l and not l.startswith("frame=")]
            error_msg = error_lines[-1] if error_lines else f"退出码 {process.returncode}"
            return EncodeResult(
                input_path=info.path,
                output_path=output,
                input_size=info.size,
                output_size=0,
                success=False,
                error=error_msg,
            )

        return EncodeResult(
            input_path=info.path,
            output_path=output,
            input_size=info.size,
            output_size=output.stat().st_size,
            success=True,
        )

    except Exception as e:
        return EncodeResult(
            input_path=info.path,
            output_path=output,
            input_size=info.size,
            output_size=0,
            success=False,
            error=str(e),
        )

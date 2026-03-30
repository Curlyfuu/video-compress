"""压缩预设档位定义"""

from dataclasses import dataclass
from enum import Enum


class Quality(str, Enum):
    HIGH = "high"
    BALANCED = "balanced"
    SMALL = "small"


@dataclass(frozen=True)
class Profile:
    """编码参数档位"""

    quality: Quality
    # VideoToolbox 硬件编码参数
    hw_quality: int  # -q:v (1-100, 越高越好)
    # libx265 软件编码参数
    sw_crf: int

    @property
    def description(self) -> str:
        descs = {
            Quality.HIGH: "高质量 — 几乎无损",
            Quality.BALANCED: "均衡 — 推荐日常使用",
            Quality.SMALL: "最小体积 — 适合分享",
        }
        return descs[self.quality]

    @property
    def expected_ratio(self) -> str:
        ratios = {
            Quality.HIGH: "2~3x",
            Quality.BALANCED: "3~5x",
            Quality.SMALL: "5~8x",
        }
        return ratios[self.quality]


PROFILES = {
    Quality.HIGH: Profile(quality=Quality.HIGH, hw_quality=65, sw_crf=24),
    Quality.BALANCED: Profile(quality=Quality.BALANCED, hw_quality=58, sw_crf=27),
    Quality.SMALL: Profile(quality=Quality.SMALL, hw_quality=48, sw_crf=30),
}

DEFAULT_QUALITY = Quality.BALANCED

# 支持的视频文件扩展名
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts", ".ts"}

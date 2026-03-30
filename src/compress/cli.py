"""CLI 入口"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .encoder import detect_hw_encoder, get_encoder_label, get_max_parallel, has_encoder
from .probe import VideoInfo, probe
from .profiles import DEFAULT_QUALITY, PROFILES, Quality
from .queue import process_batch, process_single, scan_videos, make_output_path, should_skip
from .report import print_report

app = typer.Typer(
    name="compress",
    help="运动相机视频批量压缩工具",
    add_completion=False,
)
console = Console()


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    return f"{size_bytes / 1024:.0f} KB"


@app.command()
def main(
    input_path: Path = typer.Argument(
        ...,
        help="输入视频文件或目录",
        exists=True,
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="输出目录（默认：输入路径旁的 compressed/ 目录）",
    ),
    quality: Quality = typer.Option(
        DEFAULT_QUALITY.value, "--quality", "-q",
        help="质量档位：high（高质量）/ balanced（均衡）/ small（最小体积）",
    ),
    software: bool = typer.Option(
        False, "--software", "-s",
        help="使用软件编码（libx265），压缩效率更高但速度慢",
    ),
    parallel: int = typer.Option(
        1, "--parallel", "-p",
        help="并行处理数（仅批量模式生效，建议不超过 3）",
        min=1, max=8,
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="预览模式：仅显示将要处理的文件，不实际压缩",
    ),
) -> None:
    """压缩运动相机视频，在几乎不损失画质的前提下大幅减小文件体积。"""
    input_path = input_path.resolve()
    profile = PROFILES[quality]

    # 检查编码器可用性
    if software:
        if not has_encoder("libx265"):
            console.print(
                "[red]libx265 编码器不可用。[/red]\n"
                "  请安装包含 libx265 的完整版 FFmpeg。\n"
                "  或去掉 --software 参数使用硬件编码。"
            )
            raise typer.Exit(1)
    else:
        hw = detect_hw_encoder()
        if hw is None:
            console.print(
                "[yellow]未检测到硬件编码器，自动切换到软件编码 (libx265)[/yellow]"
            )
            software = True
            if not has_encoder("libx265"):
                console.print("[red]libx265 也不可用，无法编码。请安装完整版 FFmpeg。[/red]")
                raise typer.Exit(1)

    # 确定输出目录
    if output is None:
        if input_path.is_file():
            output = input_path.parent / "compressed"
        else:
            output = input_path / "compressed"
    output = output.resolve()

    # 扫描文件
    files = scan_videos(input_path)
    if not files:
        console.print("[red]未找到视频文件[/red]")
        raise typer.Exit(1)

    # 显示配置信息
    encoder_label = get_encoder_label(software)

    # 智能并发限制
    max_p = get_max_parallel(software)
    if parallel > max_p:
        console.print(
            f"  [yellow]并发数 {parallel} 超出当前编码器建议上限 {max_p}，"
            f"已自动调整为 {max_p}[/yellow]"
        )
        parallel = max_p

    console.print()
    console.print(f"  [bold]质量档位：[/bold]{quality.value} — {profile.description}")
    console.print(f"  [bold]编码器：[/bold]{encoder_label}")
    if parallel > 1:
        console.print(f"  [bold]并发数：[/bold]{parallel}（上限 {max_p}）")
    console.print(f"  [bold]输出目录：[/bold]{output}")
    console.print(f"  [bold]文件数量：[/bold]{len(files)} 个")
    console.print()

    if dry_run:
        _dry_run(files, profile, output, software=software)
        return

    # 单文件 vs 批量
    if len(files) == 1:
        info = probe(files[0])
        out = make_output_path(files[0], output)
        skip = should_skip(info, profile, out, software=software)
        if skip:
            console.print(f"  [dim]跳过：{skip}[/dim]")
            return
        result = process_single(info, profile, out, software=software, console=console)
        print_report([result], console)
    else:
        results = process_batch(
            files, profile, output,
            software=software,
            parallel=parallel,
            console=console,
        )
        print_report(results, console)


def _dry_run(
    files: list[Path],
    profile: "Profile",
    output_dir: Path,
    *,
    software: bool,
) -> None:
    """预览模式"""
    table = Table(title="预览 — 将要处理的文件")
    table.add_column("文件", style="cyan", max_width=40)
    table.add_column("分辨率", justify="center")
    table.add_column("帧率", justify="center")
    table.add_column("编码", justify="center")
    table.add_column("码率", justify="right")
    table.add_column("大小", justify="right")
    table.add_column("状态", justify="center")

    total_size = 0
    processable = 0

    for f in files:
        try:
            info = probe(f)
            out = make_output_path(f, output_dir)
            skip = should_skip(info, profile, out, software=software)
            total_size += info.size

            if skip:
                table.add_row(
                    f.name,
                    info.resolution_label,
                    info.fps_label,
                    info.codec,
                    f"{info.bitrate_mbps:.1f} Mbps",
                    _format_size(info.size),
                    f"[dim]{skip}[/dim]",
                )
            else:
                processable += 1
                table.add_row(
                    f.name,
                    info.resolution_label,
                    info.fps_label,
                    info.codec,
                    f"{info.bitrate_mbps:.1f} Mbps",
                    _format_size(info.size),
                    "[green]待处理[/green]",
                )
        except Exception as e:
            table.add_row(f.name, "-", "-", "-", "-", "-", f"[red]{e}[/red]")

    console.print(table)
    console.print()
    console.print(f"  [bold]总大小：[/bold]{_format_size(total_size)}")
    console.print(f"  [bold]待处理：[/bold]{processable} 个")
    console.print(
        f"  [bold]预计压缩后：[/bold]约 {_format_size(int(total_size / 3))} ~ "
        f"{_format_size(int(total_size / 5))}（{profile.expected_ratio} 压缩比）"
    )
    console.print()

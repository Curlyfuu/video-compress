"""批量处理队列"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console

from .encoder import EncodeResult, encode
from .probe import VideoInfo, probe
from .profiles import VIDEO_EXTENSIONS, Profile
from .progress import create_batch_progress, create_file_progress


def scan_videos(path: Path, recursive: bool = True) -> list[Path]:
    """扫描目录下的视频文件"""
    if path.is_file():
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return [path]
        return []

    if recursive:
        files = sorted(
            f for f in path.rglob("*")
            if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
        )
    else:
        files = sorted(
            f for f in path.iterdir()
            if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
        )
    return files


def make_output_path(input_path: Path, output_dir: Path) -> Path:
    """生成输出文件路径，保持子目录结构"""
    return output_dir / input_path.name


def should_skip(info: VideoInfo, profile: Profile, output: Path, *, software: bool) -> str | None:
    """判断是否应跳过该文件，返回跳过原因或 None"""
    if output.exists() and output.stat().st_size > 0:
        return "输出文件已存在"
    return None


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    return f"{size_bytes / 1024:.0f} KB"


def process_single(
    info: VideoInfo,
    profile: Profile,
    output: Path,
    *,
    software: bool = False,
    console: Console | None = None,
) -> EncodeResult:
    """处理单个文件（带进度条）"""
    if console is None:
        console = Console()

    label = f"{info.path.name}  {info.summary}  {_format_size(info.size)}"

    progress = create_file_progress()
    with progress:
        task_id = progress.add_task(label, total=info.duration)

        def on_progress(current: float, total: float) -> None:
            progress.update(task_id, completed=current)

        result = encode(
            info, profile, output,
            software=software,
            on_progress=on_progress,
        )
        progress.update(task_id, completed=info.duration)

    return result


def process_batch(
    files: list[Path],
    profile: Profile,
    output_dir: Path,
    *,
    software: bool = False,
    parallel: int = 1,
    console: Console | None = None,
) -> list[EncodeResult]:
    """批量处理多个文件"""
    if console is None:
        console = Console()

    results: list[EncodeResult] = []

    # 先探测所有文件
    infos: list[tuple[VideoInfo, Path]] = []
    for f in files:
        try:
            info = probe(f)
            out = make_output_path(f, output_dir)
            skip = should_skip(info, profile, out, software=software)
            if skip:
                console.print(f"  [dim]跳过 {f.name}：{skip}[/dim]")
                continue
            infos.append((info, out))
        except Exception as e:
            console.print(f"  [red]探测失败 {f.name}：{e}[/red]")
            results.append(EncodeResult(
                input_path=f,
                output_path=output_dir / f.name,
                input_size=f.stat().st_size if f.exists() else 0,
                output_size=0,
                success=False,
                error=str(e),
            ))

    if not infos:
        return results

    if parallel <= 1:
        # 串行处理
        batch_progress = create_batch_progress()
        with batch_progress:
            batch_task = batch_progress.add_task("总进度", total=len(infos))
            for info, out in infos:
                batch_progress.update(batch_task, description=f"[{info.path.name}]")
                result = process_single(
                    info, profile, out,
                    software=software,
                    console=console,
                )
                results.append(result)
                batch_progress.advance(batch_task)
    else:
        # 并行处理
        def _encode_task(item: tuple[VideoInfo, Path]) -> EncodeResult:
            info, out = item
            return encode(info, profile, out, software=software)

        batch_progress = create_batch_progress()
        with batch_progress:
            batch_task = batch_progress.add_task("总进度", total=len(infos))
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {executor.submit(_encode_task, item): item for item in infos}
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    batch_progress.advance(batch_task)

    return results

"""压缩报告生成"""

from rich.console import Console
from rich.table import Table

from .encoder import EncodeResult


def _format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    return f"{size_bytes / 1024:.0f} KB"


def print_report(results: list[EncodeResult], console: Console | None = None) -> None:
    """打印压缩报告"""
    if console is None:
        console = Console()

    if not results:
        console.print("[yellow]没有处理任何文件[/yellow]")
        return

    success = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    # 详细表格
    table = Table(title="压缩报告", show_lines=False)
    table.add_column("文件", style="cyan", max_width=40)
    table.add_column("原始大小", justify="right")
    table.add_column("压缩后", justify="right")
    table.add_column("压缩比", justify="right")
    table.add_column("节省", justify="right")
    table.add_column("状态", justify="center")

    for r in results:
        if r.success:
            table.add_row(
                r.input_path.name,
                _format_size(r.input_size),
                _format_size(r.output_size),
                f"{r.ratio:.1f}x",
                f"{r.saved_percent:.0f}%",
                "[green]OK[/green]",
            )
        else:
            table.add_row(
                r.input_path.name,
                _format_size(r.input_size),
                "-",
                "-",
                "-",
                f"[red]失败[/red]",
            )

    console.print()
    console.print(table)

    # 汇总
    if success:
        total_input = sum(r.input_size for r in success)
        total_output = sum(r.output_size for r in success)
        total_saved = total_input - total_output

        console.print()
        console.print(f"  [bold]处理文件数：[/bold]{len(success)} 个")
        console.print(f"  [bold]原始总大小：[/bold]{_format_size(total_input)}")
        console.print(f"  [bold]压缩后总大小：[/bold]{_format_size(total_output)}")
        console.print(
            f"  [bold]总共节省：[/bold]{_format_size(total_saved)}"
            f" ({total_saved / total_input * 100:.0f}%)"
        )
        console.print(
            f"  [bold]平均压缩比：[/bold]{total_input / total_output:.1f}x"
        )

    if failed:
        console.print()
        console.print(f"  [bold red]失败文件数：{len(failed)}[/bold red]")
        for r in failed:
            console.print(f"    {r.input_path.name}: {r.error}")

    console.print()

"""Command-line interface for Dividend Analyzer, built with rich terminal output.
"""
import sys
import argparse
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.algorithms.factory import get_algorithm
from dividend_analyzer.data.fetcher import DataFetcher
from dividend_analyzer.data.cache import DataCache
from dividend_analyzer.excel.processor import ExcelBatchProcessor
from dividend_analyzer.visualization.charts import plot_stock_dashboard

console = Console()

def get_score_color(score: float) -> str:
    if score >= 0.70:
        return "bold green"
    elif score >= 0.45:
        return "bold yellow"
    else:
        return "bold red"

def print_result_card(res, benchmark_yield: float) -> None:
    score_style = get_score_color(res.final_score)

    header_text = Text()
    header_text.append(f"{res.symbol}", style="bold cyan")
    if res.company_name and res.company_name != res.symbol:
        header_text.append(f" - {res.company_name}", style="italic white")
    header_text.append(f"\nPrice: ${res.current_price:.2f} | Benchmark (SPY): {benchmark_yield:.2f}%", style="dim")

    summary_panel = Panel(
        Text.assemble(
            ("Algorithm: ", "bold"),
            (f"{res.algorithm_version}\n", "magenta"),
            ("Final Score: ", "bold"),
            (f"{res.final_score:.2f} / 1.00\n", score_style),
            ("Initial Score: ", "dim"),
            (f"{res.initial_score:.2f} | ", "dim"),
            ("Penalties: ", "dim"),
            (f"{res.penalties:.2f}", "dim red" if res.penalties > 0 else "dim green"),
        ),
        title=header_text,
        border_style="cyan",
    )
    console.print(summary_panel)

    # Condition breakdown table
    table = Table(title="Metric Condition Breakdown", show_header=True, header_style="bold magenta")
    table.add_column("Condition / Metric", style="cyan", no_wrap=True)
    table.add_column("Value", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Raw Score", justify="right")
    table.add_column("Weight", justify="right")

    for cond, val in res.conditions.items():
        thresh_info = res.thresholds.get(cond, (None, ""))
        thresh_str = f"{thresh_info[1]} {thresh_info[0]:.2f}" if thresh_info[0] is not None else "-"
        raw_s = res.raw_scores.get(cond, None)
        raw_s_str = f"{raw_s:.2f}" if raw_s is not None else "-"
        w = res.weights.get(cond, None)
        w_str = f"{w:.2f}" if w is not None else "-"

        table.add_row(cond, f"{val:.2f}", thresh_str, raw_s_str, w_str)

    console.print(table)

    if res.missing_dividends:
        console.print(f"[bold red][!] Missing/Irregular Dividends Detected ({len(res.missing_dividends)}):[/bold red]")
        for d in res.missing_dividends[:5]:
            console.print(f"  * {d}")
        if len(res.missing_dividends) > 5:
            console.print(f"  * ...and {len(res.missing_dividends) - 5} more")
    else:
        console.print("[dim green][OK] No missing dividend schedules detected.[/dim green]")

def handle_analyze(args):
    fetcher = DataFetcher(use_cache=not args.no_cache)
    algo = get_algorithm(args.version)
    benchmark_yield = fetcher.get_benchmark_dividend_yield()

    with console.status(f"[bold green]Fetching data for {args.symbol}..."):
        history, info = fetcher.fetch_stock_data(args.symbol)

    if history is None or info is None:
        console.print(f"[bold red]Failed to retrieve data for symbol '{args.symbol}'.[/bold red]")
        sys.exit(1)

    result = algo.analyze(args.symbol, history, info, benchmark_yield)
    print_result_card(result, benchmark_yield)

    if args.chart or args.save_chart:
        out_path = args.save_chart or (Path("charts") / f"{args.symbol}_{args.version}.png")
        plot_stock_dashboard(result, history, output_path=out_path, show=args.chart)
        console.print(f"[green]Chart saved to: {out_path}[/green]")

def handle_compare(args):
    fetcher = DataFetcher(use_cache=not args.no_cache)
    benchmark_yield = fetcher.get_benchmark_dividend_yield()

    with console.status(f"[bold green]Fetching data for {args.symbol}..."):
        history, info = fetcher.fetch_stock_data(args.symbol)

    if history is None or info is None:
        console.print(f"[bold red]Failed to retrieve data for symbol '{args.symbol}'.[/bold red]")
        sys.exit(1)

    table = Table(
        title=f"Multi-Version Algorithm Comparison: {args.symbol.upper()}",
        show_header=True,
        header_style="bold blue",
    )
    table.add_column("Version", style="bold cyan", no_wrap=True)
    table.add_column("Initial", justify="right")
    table.add_column("Penalties", justify="right")
    table.add_column("Final Score", justify="right")
    table.add_column("Key Features", style="dim")

    for version in AlgorithmVersion:
        algo = get_algorithm(version)
        res = algo.analyze(args.symbol, history, info, benchmark_yield)
        score_color = get_score_color(res.final_score)
        table.add_row(
            version.value,
            f"{res.initial_score:.2f}",
            f"{res.penalties:.2f}",
            f"[{score_color}]{res.final_score:.2f}[/{score_color}]",
            version.display_name.split(":")[-1].strip(),
        )

    console.print(table)

def handle_batch(args):
    file_path = Path(args.file)
    if not file_path.exists():
        console.print(f"[bold red]File not found: {file_path}[/bold red]")
        sys.exit(1)

    processor = ExcelBatchProcessor(default_version=AlgorithmVersion(args.version))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Processing {file_path.name}...", total=100)

        def cb(current, total, sym, res):
            score_text = f" -> {res.final_score:.2f}" if res else ""
            progress.update(task, completed=(current / total) * 100, description=f"Processing {sym}{score_text}")

        results = processor.process_file(
            file_path=file_path,
            sheet_name=args.sheet,
            version=AlgorithmVersion(args.version),
            progress_callback=cb,
        )

    console.print(f"[bold green][OK] Batch analysis complete![/bold green] Results written to {file_path}")
    for sheet, res_list in results.items():
        console.print(f"  * Sheet '{sheet}': {len(res_list)} symbols analyzed.")

def handle_versions(args):
    table = Table(title="Available Algorithm Versions", show_header=True, header_style="bold magenta")
    table.add_column("Enum Value", style="bold cyan")
    table.add_column("Display Name", style="bold white")
    table.add_column("Description", style="white")

    for v in AlgorithmVersion:
        table.add_row(v.value, v.display_name, v.description)

    console.print(table)

def handle_cache(args):
    cache = DataCache()
    if args.clear:
        cache.clear()
        console.print("[bold green][OK] Data cache cleared successfully.[/bold green]")
    else:
        console.print(f"Cache location: {cache.db_path}")

def main():
    parser = argparse.ArgumentParser(
        prog="dividend-analyzer",
        description="A professional multi-version dividend stock analysis and portfolio scoring engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # analyze
    analyze_p = subparsers.add_parser("analyze", help="Analyze a single stock symbol")
    analyze_p.add_argument("symbol", type=str, help="Stock ticker symbol (e.g. AAPL, JNJ, O)")
    analyze_p.add_argument(
        "--version",
        "-v",
        type=str,
        default=AlgorithmVersion.V5_DIVIDEND_VALUE.value,
        choices=[v.value for v in AlgorithmVersion],
        help="Algorithm version to evaluate with (default: v5_dividend_value)",
    )
    analyze_p.add_argument("--no-cache", action="store_true", help="Bypass local SQLite cache")
    analyze_p.add_argument("--chart", action="store_true", help="Display Matplotlib visual chart")
    analyze_p.add_argument("--save-chart", type=str, help="Save chart image to path")
    analyze_p.set_defaults(func=handle_analyze)

    # compare
    compare_p = subparsers.add_parser("compare", help="Compare all algorithm versions side-by-side for a stock")
    compare_p.add_argument("symbol", type=str, help="Stock ticker symbol (e.g. JNJ)")
    compare_p.add_argument("--no-cache", action="store_true", help="Bypass local SQLite cache")
    compare_p.set_defaults(func=handle_compare)

    # batch
    batch_p = subparsers.add_parser("batch", help="Batch analyze stock symbols from an Excel file")
    batch_p.add_argument("file", type=str, help="Path to Excel spreadsheet (.xlsx)")
    batch_p.add_argument("--sheet", type=str, help="Specific sheet name to process (default: all sheets)")
    batch_p.add_argument(
        "--version",
        "-v",
        type=str,
        default=AlgorithmVersion.V5_DIVIDEND_VALUE.value,
        choices=[v.value for v in AlgorithmVersion],
        help="Algorithm version to run (default: v5_dividend_value)",
    )
    batch_p.set_defaults(func=handle_batch)

    # versions
    versions_p = subparsers.add_parser("versions", help="List all available algorithm versions and specifications")
    versions_p.set_defaults(func=handle_versions)

    # cache
    cache_p = subparsers.add_parser("cache", help="Manage local SQLite cache")
    cache_p.add_argument("--clear", action="store_true", help="Clear all cached data")
    cache_p.set_defaults(func=handle_cache)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

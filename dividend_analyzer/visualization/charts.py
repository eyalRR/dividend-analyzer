"""Matplotlib chart generators for stock price, dividend trends, and condition scorecards.
"""
from pathlib import Path
from typing import Optional
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap
import pandas as pd
from dividend_analyzer.models import StockAnalysisResult

def get_condition_colormap():
    return LinearSegmentedColormap.from_list("rg", ["#ef4444", "#f59e0b", "#10b981"])

def plot_stock_dashboard(
    result: StockAnalysisResult,
    history: pd.DataFrame,
    output_path: Optional[str | Path] = None,
    show: bool = False,
) -> Optional[plt.Figure]:
    """Generate a clean visual dashboard containing price, dividends, and metric scores."""
    if history is None or history.empty:
        return None

    fig = plt.figure(figsize=(14, 10))
    gs = GridSpec(3, 1, figure=fig, height_ratios=[1.2, 1.2, 1.4])
    cmap = get_condition_colormap()

    # 1. Stock Price
    ax1 = fig.add_subplot(gs[0, 0])
    if "Close" in history.columns:
        ax1.plot(history.index, history["Close"], color="#2563eb", linewidth=1.5)
        ax1.set_title(f"{result.symbol} - Stock Price History", fontsize=11, fontweight="bold")
        ax1.set_ylabel("Price ($)", fontsize=9)
        ax1.grid(True, linestyle="--", alpha=0.5)

    # 2. Dividend History
    ax2 = fig.add_subplot(gs[1, 0])
    if "Dividends" in history.columns:
        div_history = history[history["Dividends"] > 0]
        if not div_history.empty:
            ax2.vlines(
                div_history.index,
                ymin=0,
                ymax=div_history["Dividends"],
                color="#059669",
                linewidth=2.0,
                label="Dividend Paid",
            )
            ax2.set_ylim(0, max(div_history["Dividends"]) * 1.25)
        else:
            ax2.text(0.5, 0.5, "No dividend payment records", ha="center", va="center")

        # Mark missing dividends
        if result.missing_dividends:
            missing_dates = pd.to_datetime(result.missing_dividends)
            ax2.scatter(
                missing_dates,
                [0] * len(missing_dates),
                color="#dc2626",
                marker="x",
                s=60,
                linewidth=2,
                label="Detected Missing Dividend",
                zorder=5,
            )

        ax2.set_title(f"{result.symbol} - Historical Dividend Payouts", fontsize=11, fontweight="bold")
        ax2.set_ylabel("Dividend ($)", fontsize=9)
        ax2.grid(True, linestyle="--", alpha=0.5)
        ax2.legend(loc="upper left", fontsize=8)

    # 3. Condition Scores
    ax3 = fig.add_subplot(gs[2, 0])
    if result.conditions:
        cond_names = list(result.conditions.keys())
        cond_vals = [result.conditions[k] for k in cond_names]
        scores = [result.raw_scores.get(k, 0.5) for k in cond_names]
        # Map score [-0.5, 1.0] to [0.0, 1.0] for color mapping
        norm_colors = [cmap(max(0.0, min(1.0, (s + 0.5) / 1.5))) for s in scores]

        bars = ax3.bar(cond_names, cond_vals, color=norm_colors, width=0.55)
        ax3.set_title(
            f"Score Breakdown ({result.algorithm_version}) | Final Score: {result.final_score:.2f} (Initial: {result.initial_score:.2f}, Penalties: {result.penalties:.2f})",
            fontsize=11,
            fontweight="bold",
        )
        ax3.set_ylabel("Metric Value", fontsize=9)
        ax3.tick_params(axis="x", rotation=25, labelsize=8)
        ax3.grid(True, linestyle="--", alpha=0.5, axis="y")

        # Add data labels
        for i, bar in enumerate(bars):
            val = cond_vals[i]
            score_text = f"Val: {val:.1f}\nScore: {scores[i]:.2f}"
            y_pos = max(val, 0)
            ax3.text(
                bar.get_x() + bar.get_width() / 2.0,
                y_pos + 0.05,
                score_text,
                ha="center",
                va="bottom",
                fontsize=7,
            )

    plt.tight_layout()

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out_p), dpi=150)

    if show:
        plt.show()

    return fig

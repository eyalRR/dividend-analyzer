"""
Generate a one-image snapshot for a stock symbol: weekly candles (1y),
daily candles (6m, with SMA150), and a table of percent-change over
several lookback periods.

Usage:
    python stock_snapshot.py AAPL
    python stock_snapshot.py AAPL -o aapl_snapshot.png
"""
import argparse
import math
import sys
from datetime import timedelta

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import yfinance as yf
from bidi.algorithm import get_display
from matplotlib.ticker import MultipleLocator

from tase_symbols import resolve_symbol as _resolve_tase_symbol

# (label, days back). "Days back" is calendar days; the nearest trading day
# at-or-before that date is used as the baseline price. MTD/YTD use the
# first day of the current month/year instead of a fixed day count.
LOOKBACKS = [
    ("יומית", 1),
    ("7 ימים", 7),
    ("14 ימים", 14),
    ("חודש", 30),
    ("3 חודשים", 91),
    ("6 חודשים", 182),
    ("שנה", 365),
]


def rtl(text: str) -> str:
    return get_display(text)


def normalize_symbol(symbol: str) -> str:
    # TASE (Tel Aviv Stock Exchange) securities are commonly quoted by a bare
    # security number (e.g. 1081124 for Elbit Systems) or an Israeli ISIN
    # rather than a ticker -- neither is a Yahoo symbol Yahoo's search will
    # match directly. resolve_symbol bridges via the ISIN (a pure function of
    # the security number) and Yahoo's own search endpoint; see tase_symbols.py.
    # An ordinary ticker (AAPL, TEVA.TA, ...) passes through untouched.
    return _resolve_tase_symbol(symbol.strip())


def fetch_daily(symbol: str, period: str = "2y") -> pd.DataFrame:
    # 2y by default: the daily panel only displays the last 6 months, but
    # SMA150 needs 150 prior trading days of run-up before that window, and
    # the change table looks back up to 1y -- 2y of history covers both.
    df = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False)
    if df.empty:
        raise SystemExit(f"No data returned for symbol '{symbol}'.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.DatetimeIndex(df.index.date)
    return df


def fetch_weekly_long(symbol: str) -> pd.DataFrame:
    # Only used for the 2y/3y change figures -- not charted, so a coarser
    # weekly interval over a longer span is enough and far lighter than
    # pulling 3 years of daily bars.
    df = yf.download(symbol, period="3y", interval="1wk", auto_adjust=False, progress=False)
    if df.empty:
        raise SystemExit(f"No weekly data returned for symbol '{symbol}'.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.DatetimeIndex(df.index.date)
    return df


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    weekly = daily.resample("W").agg(agg).dropna()
    return weekly


def price_asof(close: pd.Series, target_date) -> float:
    target_date = pd.Timestamp(target_date)
    price = close.asof(target_date)
    if pd.isna(price):
        price = close.iloc[0]
    return float(price)


def compute_changes(daily: pd.DataFrame) -> dict:
    close = daily["Close"]
    last = float(close.iloc[-1])
    last_date = close.index[-1]
    changes = {}

    prev = float(close.iloc[-2]) if len(close) > 1 else last
    changes["יומית"] = (last / prev - 1) * 100

    for label, days in LOOKBACKS:
        if label == "יומית":
            continue
        baseline = price_asof(close, last_date - timedelta(days=days))
        changes[label] = (last / baseline - 1) * 100

    month_start = pd.Timestamp(year=last_date.year, month=last_date.month, day=1)
    changes["מתחילת החודש"] = (last / price_asof(close, month_start) - 1) * 100

    year_start = pd.Timestamp(year=last_date.year, month=1, day=1)
    changes["מתחילת השנה"] = (last / price_asof(close, year_start) - 1) * 100

    return changes


def compute_long_changes(weekly_long: pd.DataFrame, last: float, last_date) -> dict:
    close = weekly_long["Close"]
    changes = {}
    for label, years in (("שנתיים", 2), ("3 שנים", 3)):
        baseline = price_asof(close, last_date - timedelta(days=365 * years))
        changes[label] = (last / baseline - 1) * 100
    return changes


def compute_atr14_close(close: pd.Series, period: int = 14) -> float:
    # Close-to-close ATR (not the usual High/Low/Close True Range): day-over-day
    # |close change|, averaged over the trailing `period` sessions.
    true_range = close.diff().abs()
    return float(true_range.rolling(period).mean().iloc[-1])


# Row layout for the table, matching the reference image's grid (RTL reading
# order, so each row is listed left-to-right as it should APPEAR on screen).
TABLE_ROWS = [
    ["מתחילת השנה", "מתחילת החודש", "יומית"],
    ["3 חודשים", "חודש", "14 ימים", "7 ימים"],
    ["3 שנים", "שנתיים", "שנה", "6 חודשים"],
]


def draw_table(ax, changes: dict, atr14: float, atr14_pct: float):
    ax.axis("off")
    n_logical_rows = len(TABLE_ROWS) + 1  # +1 for the ATR14 row at the bottom
    n_rows = n_logical_rows * 2  # header + value row per logical row

    cell_h = 1.0 / n_rows
    green = "#2e7d32"
    red = "#c62828"
    header_bg = "#e8dfc8"
    value_bg = "#fdf8ec"

    for r, row in enumerate(TABLE_ROWS):
        cols = len(row)
        cell_w = 1.0 / cols
        top = 1.0 - (r * 2) * cell_h
        for c, label in enumerate(row):
            x0 = c * cell_w
            pct = changes.get(label)
            color = green if (pct is not None and pct >= 0) else red
            value_text = f"{pct:+.2f}%" if pct is not None else "N/A"

            ax.add_patch(plt.Rectangle((x0, top - cell_h), cell_w, cell_h,
                                        facecolor=header_bg, edgecolor="white"))
            ax.text(x0 + cell_w / 2, top - cell_h / 2, rtl(label),
                    ha="center", va="center", fontsize=13, fontweight="bold")

            ax.add_patch(plt.Rectangle((x0, top - 2 * cell_h), cell_w, cell_h,
                                        facecolor=value_bg, edgecolor="white"))
            ax.text(x0 + cell_w / 2, top - 1.5 * cell_h, value_text,
                    ha="center", va="center", fontsize=13, fontweight="bold", color=color)

    # ATR14 (close-to-close): a volatility magnitude, not a +/- change, so it
    # gets its own full-width row rather than being squeezed into the grid above.
    atr_top = 1.0 - (len(TABLE_ROWS) * 2) * cell_h
    ax.add_patch(plt.Rectangle((0, atr_top - cell_h), 1.0, cell_h,
                                facecolor=header_bg, edgecolor="white"))
    ax.text(0.5, atr_top - cell_h / 2, "ATR14 (close)",
            ha="center", va="center", fontsize=13, fontweight="bold")

    ax.add_patch(plt.Rectangle((0, atr_top - 2 * cell_h), 1.0, cell_h,
                                facecolor=value_bg, edgecolor="white"))
    ax.text(0.5, atr_top - 1.5 * cell_h, f"{atr14:.2f}  ({atr14_pct:.2f}% of price)",
            ha="center", va="center", fontsize=13, fontweight="bold", color="#1565c0")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


def set_monthly_xticks(ax, df: pd.DataFrame):
    # mplfinance plots candles on an integer x-axis (one slot per row, no
    # weekend gaps), so ticks must be placed at row positions, not dates.
    positions, labels = [], []
    prev_month = None
    for i, d in enumerate(df.index):
        key = (d.year, d.month)
        if key != prev_month:
            positions.append(i)
            labels.append(d.strftime("%m/%y"))
            prev_month = key
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.grid(True, axis="x", which="major", color="gray", alpha=0.3, linestyle="--")


def add_pct_axis(ax, df: pd.DataFrame):
    # A secondary left-hand y-axis sharing the same data coordinates as the
    # price axis, just relabeled as % change from the first close in view.
    base = float(df["Close"].iloc[0])
    to_pct = lambda price: (price / base - 1) * 100
    to_price = lambda pct: (pct / 100 + 1) * base

    secax = ax.secondary_yaxis("left", functions=(to_pct, to_price))
    secax.set_ylabel("% change")
    secax.yaxis.set_major_locator(MultipleLocator(5))

    # secax is only a thin strip for the ticks/labels, not a full overlay --
    # its own grid() would only be visible in that sliver. Draw the actual
    # horizontal gridlines on the main axes instead, at the same 5% levels.
    ymin, ymax = ax.get_ylim()
    start = math.floor(to_pct(ymin) / 5) * 5
    end = math.ceil(to_pct(ymax) / 5) * 5
    for level in range(int(start), int(end) + 5, 5):
        price = to_price(level)
        if ymin <= price <= ymax:
            ax.axhline(price, color="gray", alpha=0.3, linestyle="--", linewidth=0.8, zorder=0)
    ax.set_ylim(ymin, ymax)


def build_snapshot(symbol: str, out_path: str):
    daily = fetch_daily(symbol)  # 2y, for SMA150 run-up + the 1y change table
    daily_1y = daily[daily.index >= (daily.index[-1] - pd.Timedelta(days=365))]
    weekly = to_weekly(daily_1y)
    changes = compute_changes(daily_1y)

    weekly_long = fetch_weekly_long(symbol)
    last = float(daily["Close"].iloc[-1])
    last_date = daily.index[-1]
    changes.update(compute_long_changes(weekly_long, last, last_date))

    sma150 = daily["Close"].rolling(150).mean()
    daily_6m = daily[daily.index >= (daily.index[-1] - pd.DateOffset(months=6))]
    sma150_6m = sma150.reindex(daily_6m.index)

    atr14 = compute_atr14_close(daily["Close"])
    atr14_pct = atr14 / last * 100

    fig = plt.figure(figsize=(12, 14), facecolor="#fdf8ec")
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 3, 2], hspace=0.35)

    ax_weekly = fig.add_subplot(gs[0])
    ax_daily = fig.add_subplot(gs[1])
    ax_table = fig.add_subplot(gs[2])

    style = mpf.make_mpf_style(base_mpf_style="yahoo", facecolor="#fdf8ec", figcolor="#fdf8ec")

    mpf.plot(weekly, type="candle", ax=ax_weekly, style=style, volume=False, show_nontrading=False)
    ax_weekly.set_title(f"{symbol} -- Weekly candles (1y)", fontsize=14)
    set_monthly_xticks(ax_weekly, weekly)
    add_pct_axis(ax_weekly, weekly)

    mpf.plot(daily_6m, type="candle", ax=ax_daily, style=style, volume=False, show_nontrading=False)
    ax_daily.plot(range(len(daily_6m)), sma150_6m.values, color="#1565c0", linewidth=1.3, label="SMA150")
    ax_daily.legend(loc="upper left", fontsize=9, frameon=False)
    ax_daily.set_title(f"{symbol} -- Daily candles (6m)", fontsize=14)
    set_monthly_xticks(ax_daily, daily_6m)
    add_pct_axis(ax_daily, daily_6m)

    draw_table(ax_table, changes, atr14, atr14_pct)

    fig.suptitle(symbol, fontsize=18, fontweight="bold")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="Ticker symbol, e.g. AAPL, TEVA.TA, or a bare TASE security number like 629014")
    parser.add_argument("-o", "--output", default=None, help="Output image path (default: <symbol>_snapshot.png)")
    args = parser.parse_args()

    symbol = normalize_symbol(args.symbol)
    out_path = args.output or f"{symbol.replace('.', '_')}_snapshot.png"
    path = build_snapshot(symbol, out_path)
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()

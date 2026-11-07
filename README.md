# Dividend Analyzer

A professional, modular Python dividend stock analysis, portfolio scoring, and batch evaluation engine.

---

## Overview

**Dividend Analyzer** unifies multiple historical generations of dividend scoring models into a single, clean software package. Built with the **Strategy** and **Factory** design patterns, it allows you to evaluate any stock or batch-process portfolios across all algorithm versions using an `AlgorithmVersion` Enum.

### Key Capabilities
- **Multi-Version Scoring**: Choose which algorithm version to execute on-demand (`V1_LINEAR` through `V6_MODERN_CORRECTED`).
- **Side-by-Side Comparison**: Compare how different algorithm generations score the same stock in a single command.
- **Transparent Local Caching**: SQLite-backed caching layer (`dividend_cache.db`) with TTL management prevents Yahoo Finance rate limiting and speeds up batch runs by $>85\%$.
- **Batch Excel Processing**: Seamlessly updates Excel workbooks (`.xlsx`) across multiple sheets (`onezero`, `pepper`, `spy`, `nyse`), recording final scores and timestamps.
- **Visual Charting**: Generates Matplotlib dashboards displaying price trends, dividend payment history with missing dividend detection, and colored scorecard bars.
- **Automated Test Suite**: Complete unit test coverage powered by `pytest`.

---

## Directory Structure

```text
DIVIDENS/
├── dividend_analyzer/                # Core Python Package
│   ├── __init__.py                   # Package exports
│   ├── cli.py                        # Terminal CLI powered by rich
│   ├── config.py                     # Config constants, cache paths, default TTLs
│   ├── models.py                     # Typed DataClasses (StockAnalysisResult, etc.)
│   ├── data/
│   │   ├── cache.py                  # Persistent SQLite caching engine
│   │   └── fetcher.py                # Yahoo Finance fetcher with caching
│   ├── algorithms/
│   │   ├── versions.py               # AlgorithmVersion Enum definition
│   │   ├── base.py                   # BaseAlgorithm abstract class
│   │   ├── factory.py                # Factory to instantiate algorithm by Enum
│   │   ├── v1_linear.py              # Normalized linear scoring [-1, 1]
│   │   ├── v2_sigmoid.py             # Logistic sigmoid S-curve model
│   │   ├── v3_exponential.py         # Asymmetric exponential & quadratic curves
│   │   ├── v4_penalty.py             # Weighted multi-factor safety penalties
│   │   ├── v5_dividend_value.py      # Compounded Dividend Value model (Baseline)
│   │   └── v6_modern.py              # Modern financial standard (Corrected math)
│   ├── excel/
│   │   └── processor.py              # Multi-sheet Excel reader & writer
│   └── visualization/
│       └── charts.py                 # Matplotlib dashboard generator
├── tests/                            # Pytest automated test suite
│   ├── conftest.py                   # Shared synthetic test fixtures
│   ├── test_algorithms.py            # Algorithm verification tests
│   ├── test_cache.py                 # SQLite cache hit/miss tests
│   └── test_excel.py                 # Excel read/write verification
├── data/                             # Working datasets (divList.xlsx, SP500, etc.)
├── charts/                           # Generated chart images
├── archive/                          # Archived legacy prototypes (Flask, React, etc.)
├── pyproject.toml                    # Modern PEP 518/621 packaging metadata
├── requirements.txt                  # Lean project dependencies
└── README.md                         # Documentation
```

---

## Input → Processing → Output Flow

The core engine (not the one-off `scripts/`, covered below) follows one pipeline regardless of entry point (`analyze`, `compare`, or `batch`):

1. **Input**
   - A single ticker symbol (CLI arg) or a batch of symbols read from an Excel workbook (`data/divList.xlsx`, etc. — any sheet with a `symbol`/`ticker` column).
   - `--version` selects which of the 6 algorithm strategies to score with (default `v5_dividend_value`).

2. **Fetch** (`dividend_analyzer/data/fetcher.py`)
   - `DataFetcher.fetch_stock_data()` pulls price/dividend history and fundamentals from `yfinance`, transparently reading/writing through the SQLite-backed `DataCache` (`dividend_cache.db`) to avoid redundant Yahoo Finance calls.
   - `get_benchmark_dividend_yield()` fetches SPY's trailing yield once per run as the scoring benchmark.

3. **Score** (`dividend_analyzer/algorithms/*`)
   - The selected `BaseAlgorithm` subclass (`v1_linear` … `v6_modern`) consumes `(history, info, benchmark_yield)` and produces a `StockAnalysisResult` — final/initial score, penalties, per-metric conditions, raw scores, weights, and any detected missing dividends.

4. **Output**
   - **CLI** (`cli.py`): `rich` panels/tables for `analyze` (single-stock breakdown) and `compare` (all 6 versions side-by-side).
   - **Excel writeback** (`excel/processor.py`): `batch` writes `score`/`date` columns back into the source workbook in place.
   - **Charts** (`visualization/charts.py`): `plot_stock_dashboard()` renders a 3-panel Matplotlib dashboard (price, dividend history with missing-dividend markers, metric score bars), optionally saved to PNG.

```
symbol(s) ──► DataFetcher (yfinance + SQLite cache) ──► Algorithm (Strategy) ──► StockAnalysisResult
                                                                                        │
                                                              ┌─────────────────────────┼─────────────────────────┐
                                                              ▼                         ▼                         ▼
                                                        CLI tables (rich)      Excel writeback (score/date)   PNG dashboard
```

---

## Utility Scripts (`scripts/`)

These are standalone maintenance/reporting scripts, separate from the core package above. They are **not** interdependent in code, but refreshing the project's data end-to-end follows this order:

1. **`update_sp500.py`** — Run first. Pulls the current S&P 500 constituent list from Wikipedia and rebuilds:
   - `data/SP500_Companies.xlsx` — full reference list of all current constituents.
   - `data/divList.xlsx` — filtered down to constituents that paid a dividend in the trailing 5 years (overwrites the file).
   ```powershell
   python scripts/update_sp500.py
   ```

2. **`add_new_dividend_payers.py`** — Run second, after `update_sp500.py` (or whenever you want to extend the watchlist with tickers from outside the S&P 500). Combines external ticker lists (currently `market_dashboard`'s `ALL_STOCKS` and a `good_fundamental` screener CSV), skips anything already in `data/divList.xlsx`, filters the rest for a dividend paid in the trailing 5 years, and **appends** the qualifying tickers to `data/divList.xlsx`.
   ```powershell
   python scripts/add_new_dividend_payers.py
   ```

3. **`export_scores.py`** — Run last, once the watchlist is finalized. Takes any comma-separated ticker list and scores every symbol across all 6 algorithm versions, writing one row per symbol to a single CSV.
   ```powershell
   python scripts/export_scores.py MSFT,AAPL,GOOG,ARM --out scores.csv
   ```

All three scripts use `dividend_analyzer.data.fetcher.DataFetcher` for any Yahoo Finance access rather than calling `yfinance` directly, keeping fetch logic (timezone handling, etc.) consistent with the core package.

---

## Algorithm Versions Catalog

| Version Enum | Name | Description | Key Features |
|---|---|---|---|
| `v1_linear` | **V1: Normalized Linear** | Initial 7-metric model | Maps metrics linearly to $[-1, 1]$ against fixed thresholds. Equal weighting. |
| `v2_sigmoid` | **V2: Sigmoid S-Curve** | Logistic sigmoid model | $S(x) = 1 / (1 + e^{-x})$. Tighter payout ($<50\%$) and dividend growth ($>10\%$) thresholds. |
| `v3_exponential` | **V3: Asymmetric Exponential** | Benchmark-driven curves | Dynamic S&P 500 (`SPY`) dividend yield benchmark. Asymmetric quadratic curve for payout & debt-to-equity; exponential for growth. 7 weighted metrics. |
| `v4_penalty_weighted` | **V4: Safety Penalties** | Risk-deduction model | Adds penalties for dangerous payout ($\ge 80\%$), low earnings growth ($\le 3\%$), excessive leverage ($\ge 2.0$), and low age ($\le 5$ yrs). Bonus for yield $> 2\times$ SPY. |
| `v5_dividend_value` | **V5: Dividend Value (Baseline)** | Compounded yield + growth | Combines yield and growth into 5-year compounded **Dividend Value** ($40\%$ weight). Multi-sheet Excel support (`divClaude5.py`/`excel.py`). |
| `v6_modern_corrected` | **V6: Modern Financial Standard** | Production corrected standard | **TTM yield** (trailing 365 days), **true earnings growth** from financial statements, **true diluted EPS**, **full dividend age** (no 10-year cap), and **unprofitable company protection**. |

---

## Installation & Setup

1. **Clone or Navigate to the Repository**:
   ```powershell
   cd c:\Users\EYAL\Desktop\DIVIDENS
   ```

2. **Install Dependencies**:
   ```powershell
   python -m pip install -r requirements.txt
   ```

3. **Install Package in Editable Mode (Optional)**:
   ```powershell
   python -m pip install -e .
   ```

---

## CLI Usage

### 1. Analyze a Single Stock
Evaluate any ticker symbol using the baseline algorithm (`v5_dividend_value`):
```powershell
python -m dividend_analyzer.cli analyze JNJ
```

Specify a different algorithm version:
```powershell
python -m dividend_analyzer.cli analyze JNJ --version v6_modern_corrected
```

Generate and save a visual chart:
```powershell
python -m dividend_analyzer.cli analyze JNJ --save-chart charts/JNJ_dashboard.png
```

### 2. Multi-Version Comparison Mode
Compare how all 6 algorithm generations score a stock side-by-side:
```powershell
python -m dividend_analyzer.cli compare JNJ
```

### 3. Batch Excel Processing
Process an entire Excel spreadsheet, update scores and timestamps in-place:
```powershell
python -m dividend_analyzer.cli batch data/divList.xlsx --version v5_dividend_value
```

Specify a particular sheet:
```powershell
python -m dividend_analyzer.cli batch data/divList.xlsx --sheet Sheet1 --version v6_modern_corrected
```

### 4. Inspect Available Algorithm Versions
```powershell
python -m dividend_analyzer.cli versions
```

### 5. Manage Local Cache
View cache location or clear stale cache entries:
```powershell
python -m dividend_analyzer.cli cache
python -m dividend_analyzer.cli cache --clear
```

---

## Python API Usage

You can easily integrate the dividend analyzer into your own Python scripts:

```python
from dividend_analyzer import get_algorithm, AlgorithmVersion, DataFetcher

# 1. Initialize data fetcher (uses SQLite cache automatically)
fetcher = DataFetcher()

# 2. Fetch stock data and S&P 500 benchmark yield
history, info = fetcher.fetch_stock_data("JNJ")
benchmark_yield = fetcher.get_benchmark_dividend_yield("SPY")

# 3. Instantiate your desired algorithm version via Enum
algo_v5 = get_algorithm(AlgorithmVersion.V5_DIVIDEND_VALUE)
algo_v6 = get_algorithm(AlgorithmVersion.V6_MODERN_CORRECTED)

# 4. Run analysis
result_v5 = algo_v5.analyze("JNJ", history, info, benchmark_yield)
result_v6 = algo_v6.analyze("JNJ", history, info, benchmark_yield)

print(f"V5 Score: {result_v5.final_score:.2f}")
print(f"V6 Score: {result_v6.final_score:.2f}")
print("V6 Conditions:", result_v6.conditions)
```

---

## Running Automated Tests

Run the full pytest suite to verify all algorithm calculations, data caching, and Excel processing:
```powershell
python -m pytest tests/ -v
```

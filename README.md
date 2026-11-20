# Dividend Analyzer & Financial Intelligence Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Architecture](https://img.shields.io/badge/design%20patterns-Strategy%20%7C%20Factory%20%7C%20Cache--Aside-orange.svg)](#software-architecture--design-patterns)
[![Telegram Bot](https://img.shields.io/badge/telegram-interactive%20bot-0088cc.svg?logo=telegram&logoColor=white)](#1-interactive-telegram-bot)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)

An enterprise-grade, modular financial analytics and dividend scoring platform. Unifying multiple generations of quantitative dividend algorithms (V1–V6), deep fundamental solvency checks (V7), an interactive 24/7 Telegram bot, batch Excel synchronization, and containerized cloud deployment.

---

## Table of Contents
- [System Architecture & Design Patterns](#system-architecture--design-patterns)
- [Core Feature Highlights](#core-feature-highlights)
- [Algorithm Catalog (V1–V7)](#algorithm-catalog-v1v7)
- [Real-World Usage Examples](#real-world-usage-examples)
  - [1. Interactive Telegram Bot](#1-interactive-telegram-bot)
  - [2. Terminal CLI](#2-terminal-cli)
  - [3. Programmatic Python SDK](#3-programmatic-python-sdk)
  - [4. Batch Universe Scanning & Excel Sync](#4-batch-universe-scanning--excel-sync)
- [Production Docker Deployment](#production-docker-deployment)
- [Repository Structure](#repository-structure)
- [Automated Testing](#automated-testing)

---

## System Architecture & Design Patterns

The system is engineered around strict **Separation of Concerns (SoC)**, **Dependency Inversion**, and clean object-oriented architecture.

```mermaid
flowchart TD
    subgraph Presentation_Layer [Presentation Layer]
        CLI["Rich Terminal CLI (cli.py)"]
        TGBot["Telegram Bot (telegram_bot.py)"]
        ExcelBatch["Batch Excel Processor (processor.py)"]
    end

    subgraph Service_Orchestration [Service & Application Layer]
        BotCommands["Bot Commands & Menu Handler"]
        ChatSettings["Per-Chat Settings Registry (JSON)"]
        VizEngine["Chart & Snapshot Generator (Matplotlib / RTL)"]
        ExportEngine["Universe Scanning & Pipeline Orchestrator"]
    end

    subgraph Core_Domain [Core Domain & Analytics Engine]
        AlgoFactory["Algorithm Factory (factory.py)"]
        BaseAlgo["<<abstract>> BaseAlgorithm"]
        
        V1["V1: Normalized Linear"]
        V2["V2: Sigmoid S-Curve"]
        V3["V3: Asymmetric Exponential"]
        V4["V4: Penalty Weighted"]
        V5["V5: Dividend Value (Baseline)"]
        V6["V6: Modern Financial Standard"]
        V7["V7: Fundamental Solvency Check"]
    end

    subgraph Data_Layer [Data & Infrastructure Layer]
        Fetcher["DataFetcher (fetcher.py)"]
        Cache["SQLite Cache-Aside Engine (dividend_cache.db)"]
        YahooAPI["Yahoo Finance API (yfinance)"]
        TASE["TASE Symbol Resolver & Hebrew Adapter"]
    end

    %% Wiring
    CLI --> AlgoFactory
    CLI --> Fetcher
    TGBot --> BotCommands
    TGBot --> ChatSettings
    BotCommands --> AlgoFactory
    BotCommands --> VizEngine
    ExcelBatch --> AlgoFactory
    ExcelBatch --> Fetcher

    AlgoFactory --> BaseAlgo
    BaseAlgo <|-- V1
    BaseAlgo <|-- V2
    BaseAlgo <|-- V3
    BaseAlgo <|-- V4
    BaseAlgo <|-- V5
    BaseAlgo <|-- V6
    BaseAlgo <|-- V7

    Fetcher --> Cache
    Cache --> YahooAPI
    TGBot --> TASE
```

### Key Architectural Patterns

1. **Strategy Pattern (`dividend_analyzer.algorithms.*`)**:
   All valuation algorithms inherit from `BaseAlgorithm` and expose a unified interface:
   $$\text{analyze}(\text{symbol}, \text{history}, \text{info}, \text{benchmark\_yield}) \longrightarrow \text{StockAnalysisResult}$$
   Algorithms are fully decoupled from data fetching and presentation. New financial models can be plugged in without altering existing code.

2. **Factory Pattern (`dividend_analyzer.algorithms.factory`)**:
   Dynamic algorithm resolution driven by the type-safe `AlgorithmVersion` Enum. Callers instantiate models on-demand without hardcoded class bindings.

3. **Cache-Aside Pattern (`dividend_analyzer.data.cache`)**:
   A transparent SQLite caching engine (`dividend_cache.db`) intercepting all external network requests.
   - Configurable per-table TTL (Time-To-Live).
   - Eliminates rate-limiting barriers and cuts batch runtime by **$>85\%$**.

4. **Bi-Directional Text & Localization Adapter (`telegram_bot.stock_snapshot` / `tase_symbols`)**:
   Automated symbol normalization for the Tel Aviv Stock Exchange (TASE) paired with RTL text shaping (`python-bidi`) ensures flawless right-to-left Hebrew rendering across financial charts on Matplotlib.

5. **Cloud-Native Containerization (`Dockerfile` & `docker-compose.yml`)**:
   Packaged as a lightweight container using `python:3.11-slim` and Astral's `uv` package manager, ensuring identical behavior across local machines and cloud server VMs with zero environmental drift.

---

## Core Feature Highlights

- **Multi-Generational Quantitative Scoring**: Compare 7 distinct scoring strategies side-by-side on any ticker.
- **Deep Fundamental Solvency Check (V7)**: Evaluates 40+ quantitative balance-sheet metrics (Piotroski F-Score, Altman Z''-Score, Beneish M-Score, debt coverage, earnings quality).
- **Interactive 24/7 Telegram Bot**: Delivers on-demand stock summaries, interactive algorithm selection, and graphical dashboards.
- **Automated Visualization**: Generates 3-panel Matplotlib dashboards covering price trends, dividend stability timelines, missing dividend detection, and colored scorecard bars.
- **Production-Ready Persistence**: Preserves cache, user settings, audit logs, and data workbooks across reboots via Docker volume mounts.

---

## Algorithm Catalog (V1–V7)

| Version | Name | Primary Methodology | Key Target Metrics |
|---|---|---|---|
| `v1_linear` | **Normalized Linear** | Equal-weighted linear metric normalization $[-1, 1]$ | Dividend Yield, Payout Ratio, 5Y Dividend Growth, PE, Debt/Equity, Beta |
| `v2_sigmoid` | **Sigmoid S-Curve** | Logistic activation function $S(x) = \frac{1}{1 + e^{-x}}$ | Strict payout penalties ($<50\%$), dividend growth sensitivity ($>10\%$) |
| `v3_exponential` | **Asymmetric Exponential** | Benchmark-adjusted curves against S&P 500 (`SPY`) | Asymmetric quadratic penalties for payout & leverage; dynamic S&P 500 hurdle |
| `v4_penalty_weighted` | **Safety Penalty Model** | Base weighted scoring with severe tail-risk penalties | Severe deductions for payout $>80\%$, debt $>2.0$, and dividend history $<5$ years |
| `v5_dividend_value` | **Compounded Dividend Value** | Compound Yield + Growth calculation over 5-year horizon | Yield-on-Cost projection ($40\%$ weight), safety checks, and balance sheet quality |
| `v6_modern_corrected` | **Modern Financial Standard** | Mathematically rigorous trailing-twelve-month (TTM) model | Uncapped dividend age, true diluted EPS, statement earnings growth, loss protection |
| `v7_fundamental_check` | **Fundamental Solvency Engine** | Multi-pillar corporate health & solvency validation | Piotroski 9/9, Altman Z'', Beneish M, cash conversion cycle, debt coverage ratios |

---

## Real-World Usage Examples

### 1. Interactive Telegram Bot

The bot connects directly to Telegram Gateway via event-driven long polling (zero inbound firewall ports required) and supports full interactive command handling.

#### Bot Commands & Workflow

```text
User  ──►  /start       ──►  Bot welcomes user and registers chat in registry
User  ──►  /settings    ──►  Bot presents interactive algorithm choice buttons
User  ──►  AAPL         ──►  Bot fetches real-time data, generates chart & returns analysis
```

#### Example Output in Telegram Chat
When a user sends `AAPL` or `MSFT`, the bot dispatches:
1. **High-Resolution Stock Snapshot PNG**: Visual price chart, volume profile, moving averages, and key trading stats.
2. **Dividend / Fundamental Dashboard PNG**: Historical payout consistency, yield-on-cost trajectory, and score condition breakdown.
3. **Structured Financial Report**:
```text
Apple Inc. (AAPL)
Sector: Technology / Consumer Electronics
Algorithm: V7 Fundamental Check

QUALITY: 100 / 100 (Strong)    RISK: 4 / 100 (Low)

GREEN FLAGS:
  + Operating margin: 33.0% (Benchmark >= 10%)
  + ROIC: 96.8% (Benchmark >= 12%)
  + Cash Flow from Operations: $145.10B TTM (+30.2% YoY)
  + Net Debt / EBITDA: 0.26x (Safe < 3.0)
  + Piotroski F-Score: 9 / 9
  + Altman Z''-Score: 3.20 (Safe distress-free zone)

VALUATION:
  P/E: 39.0 | P/FCF: 37.9 | EV/EBITDA: 30.3 | P/B: 46.0
```

---

### 2. Terminal CLI

The CLI is powered by `rich`, featuring formatted tables, progress indicators, and color-coded status badges.

#### A. Single Stock Evaluation
```bash
# Run baseline V5 analysis
python -m dividend_analyzer.cli analyze JNJ

# Run with modern financial standard (V6) and export high-res dashboard
python -m dividend_analyzer.cli analyze JNJ --version v6_modern_corrected --save-chart charts/JNJ_dashboard.png
```

#### B. Side-by-Side Multi-Version Comparison
Compare how every generation of the algorithm evaluates the exact same company:
```bash
python -m dividend_analyzer.cli compare MSFT
```
*Output:*
```text
┌───────────────────────┬────────────┬───────────────┬───────────────────────────────┐
│ Algorithm Version     │ Score      │ Rating        │ Primary Driver                │
├───────────────────────┼────────────┼───────────────┼───────────────────────────────┤
│ v1_linear             │ 74.2 / 100 │ Favorable     │ Standard linear bounds        │
│ v2_sigmoid            │ 81.0 / 100 │ Strong        │ High growth in S-curve        │
│ v3_exponential        │ 78.5 / 100 │ Strong        │ Outperformed SPY benchmark    │
│ v4_penalty_weighted   │ 85.0 / 100 │ Strong Buy    │ Zero risk penalties triggered │
│ v5_dividend_value     │ 88.4 / 100 │ Exceptional   │ 5Y Compound Dividend Value    │
│ v6_modern_corrected   │ 86.1 / 100 │ Exceptional   │ Statement TTM earnings growth │
└───────────────────────┴────────────┴───────────────┴───────────────────────────────┘
```

#### C. In-Place Batch Excel Processing
Score hundreds of tickers stored in an Excel workbook across multiple sheets (`onezero`, `pepper`, `spy`, `nyse`):
```bash
python -m dividend_analyzer.cli batch data/divList.xlsx --version v6_modern_corrected
```

---

### 3. Programmatic Python SDK

You can import and integrate the engine into any Python pipeline:

```python
from dividend_analyzer import DataFetcher, get_algorithm, AlgorithmVersion

# 1. Initialize data fetcher with automated caching
fetcher = DataFetcher()

# 2. Retrieve cached/live financial metrics
history, info = fetcher.fetch_stock_data("TXN")
benchmark_yield = fetcher.get_benchmark_dividend_yield("SPY")

# 3. Instantiate algorithm strategies via factory
v5_algo = get_algorithm(AlgorithmVersion.V5_DIVIDEND_VALUE)
v6_algo = get_algorithm(AlgorithmVersion.V6_MODERN_CORRECTED)

# 4. Execute calculations
res_v5 = v5_algo.analyze("TXN", history, info, benchmark_yield)
res_v6 = v6_algo.analyze("TXN", history, info, benchmark_yield)

print(f"TXN V5 Score: {res_v5.final_score:.2f}")
print(f"TXN V6 Score: {res_v6.final_score:.2f}")
print(f"Passed Conditions: {res_v6.conditions}")
```

---

### 4. Batch Universe Scanning & Excel Sync

Run the complete stock screener and database refresh pipeline end-to-end:

```bash
# 1. Update reference lists of S&P 500 and Nasdaq-100 constituents
python scripts/update_sp500_nasdaq.py

# 2. Discover new dividend payers from screeners and append to watchlist
python scripts/add_new_dividend_payers.py

# 3. Batch score all symbols and generate a unified CSV matrix
python scripts/export_scores.py --from-xlsx data/divList.xlsx --out scores.csv

# Or run all 3 pipeline stages automatically in one orchestrator:
python scripts/full_universe_scan.py
```

---

## Production Docker Deployment

The application includes an optimized, production-hardened `Dockerfile` and `docker-compose.yml` configured for continuous 24/7 background execution.

### Architectural Highlights of the Container
- **Multi-Stage Speed with `uv`**: Uses Astral's `uv` binary to install dependencies in $<20$ seconds with minimal image size.
- **Embedded Font Support**: Includes `fonts-dejavu-core` and `fonts-freefont-ttf` for RTL Hebrew rendering.
- **Stateless Container with State-Preserving Mounts**: All databases, settings, and logs survive container rebuilds.

### Launching the Bot with Docker Compose

```bash
# 1. Prepare environment variables
cp .env.example .env  # Add your TELEGRAM_BOT_TOKEN

# 2. Build and launch in detached mode
docker compose up -d --build

# 3. Inspect real-time execution logs
docker compose logs -f

# 4. Check resource utilization
docker stats --no-stream
```

### `docker-compose.yml` Architecture Reference
```yaml
services:
  dividend-bot:
    build: .
    container_name: dividend-report-bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      # Data persistence across image rebuilds
      - ./data:/app/data
      - ./dividend_cache.db:/app/dividend_cache.db
      - ./telegram_bot/chat_settings.json:/app/telegram_bot/chat_settings.json
      - ./telegram_bot/logs:/app/telegram_bot/logs
```

---

## Repository Structure

```text
DIVIDENS/
├── .claude/skills/fundamental-check/ # Vendored V7 Fundamental Check Engine
│   ├── fundamental_check.py          # 40+ quantitative financial solvency tests
│   └── rulebook.md                   # Complete valuation & risk rules specification
├── dividend_analyzer/                # Core Python Package
│   ├── algorithms/                   # Strategy Pattern scoring engines
│   │   ├── base.py                   # BaseAlgorithm abstract class
│   │   ├── factory.py                # Dynamic Strategy Factory
│   │   ├── versions.py               # AlgorithmVersion Enum
│   │   ├── v1_linear.py ... v6_modern.py
│   │   └── v7_fundamental_check.py
│   ├── data/                         # Data layer & caching
│   │   ├── cache.py                  # SQLite TTL Cache Engine
│   │   └── fetcher.py                # Resilient Yahoo Finance client
│   ├── excel/                        # Multi-sheet Excel workbook processor
│   ├── visualization/                # Matplotlib dashboard generators
│   └── cli.py                        # Rich interactive terminal interface
├── telegram_bot/                     # Interactive Telegram Service
│   ├── telegram_bot.py               # Main bot service & long-polling loop
│   ├── bot_commands.py               # Command dispatching (/start, /settings)
│   ├── chat_settings.py              # Per-chat algorithm preference persistence
│   ├── stock_snapshot.py             # RTL-compatible snapshot generator
│   └── tase_symbols.py               # Tel Aviv Stock Exchange symbol mapping
├── scripts/                          # Universe refresh & CSV export pipelines
├── tests/                            # Automated Pytest suite
├── Dockerfile                        # Multi-stage production container definition
├── docker-compose.yml                # Service orchestration & volume mounting
├── requirements.txt                  # Core dependencies
└── README.md                         # Project documentation
```

---

## Automated Testing

The project maintains comprehensive test coverage across all algorithm implementations, caching mechanisms, and data serialization.

```bash
# Execute the full pytest test suite
python -m pytest tests/ -v
```

---

## License

This project is licensed under the MIT License.

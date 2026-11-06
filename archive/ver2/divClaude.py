import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime, timedelta

def fetch_stock_data(symbol, years=10):
    try:
        stock = yf.Ticker(symbol)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        history = stock.history(start=start_date, end=end_date)
        info = stock.info
        
        # Convert history index to timezone-naive
        history.index = history.index.tz_localize(None)
        
        return history, info
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None, None

def calculate_dividend_growth_rate(history):
    if history is None or history.empty or "Dividends" not in history.columns:
        return 0
    
    annual_dividends = history["Dividends"].groupby(history.index.year).sum()
    current_year = datetime.now().year
    annual_dividends = annual_dividends[annual_dividends.index < current_year]
    
    if len(annual_dividends) < 5:
        return 0
    
    start_year, end_year = annual_dividends.index[-5], annual_dividends.index[-1]
    start_value, end_value = annual_dividends[start_year], annual_dividends[end_year]
    
    years = end_year - start_year
    if start_value > 0 and years > 0:
        cagr = (end_value / start_value) ** (1 / years) - 1
        return cagr * 100
    
    return 0

def calculate_earnings_growth(history):
    if history is None or history.empty or "Close" not in history.columns:
        return 0
    
    annual_close = history["Close"].resample("Y").last().dropna()
    current_year = datetime.now().year
    annual_close = annual_close[annual_close.index.year < current_year]
    
    if len(annual_close) < 5:
        return 0
    
    start_value, end_value = annual_close.iloc[-5], annual_close.iloc[-1]
    years = 5
    
    if start_value > 0:
        cagr = (end_value / start_value) ** (1 / years) - 1
        return cagr * 100
    
    return 0

def calculate_dividend_yield(history, info):
    if history is None or history.empty or "Dividends" not in history.columns:
        return 0
    
    current_year = datetime.now().year
    last_full_year = current_year - 1
    last_year_dividends = history[history.index.year == last_full_year]["Dividends"].sum()
    
    current_price = info.get("currentPrice", 0)
    if current_price > 0:
        return (last_year_dividends / current_price) * 100
    
    return 0

def calculate_payout_ratio(history, info):
    if history is None or history.empty or "Dividends" not in history.columns:
        return 0
    
    current_year = datetime.now().year
    last_full_year = current_year - 1
    last_year_dividends = history[history.index.year == last_full_year]["Dividends"].sum()
    
    eps = info.get("trailingEps", 0)
    if eps > 0:
        return (last_year_dividends / eps) * 100
    
    return 0

def calculate_dividend_age(history):
    if history is None or history.empty or "Dividends" not in history.columns:
        return 0
    
    dividend_dates = history[history["Dividends"] > 0].index
    if len(dividend_dates) == 0:
        return 0
    
    first_dividend_date = dividend_dates.min()
    dividend_age = (datetime.now() - first_dividend_date).days / 365.25
    
    return round(dividend_age, 2)

def calculate_eps_growth(symbol):
    try:
        stock = yf.Ticker(symbol)
        
        # Fetch stock info
        info = stock.info
        
        # Check if trailing EPS is available
        if 'trailingEps' not in info:
            print(f"Trailing EPS not found for {symbol}. Skipping EPS growth calculation.")
            return 0
        
        # Get the current trailing EPS
        current_eps = info['trailingEps']
        
        # Fetch historical data for the past 5 years
        start_date = (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        history = stock.history(start=start_date, end=end_date)
        
        if history.empty:
            print(f"No historical data available for {symbol} in the past 5 years.")
            return 0
        
        # Get the closing price from 5 years ago
        past_close = history['Close'].iloc[0]
        
        # Calculate the approximate past EPS based on the past closing price
        past_eps = past_close * current_eps / info['previousClose']
        
        # Calculate the EPS growth rate
        eps_growth = (current_eps / past_eps) ** (1/5) - 1
        eps_growth_rate = eps_growth * 100
        
        print(f"Current Trailing EPS: {current_eps}")
        print(f"Approximate Past EPS (5 years ago): {past_eps}")
        print(f"EPS Growth Rate: {eps_growth_rate:.2f}%")
        
        return eps_growth_rate
    except Exception as e:
        print(f"Error calculating EPS growth for {symbol}: {e}")
        return 0

def check_conditions(symbol, history, info):
    conditions = {
        "Dividend Yield (%)": calculate_dividend_yield(history, info),
        "Payout Ratio (%)": calculate_payout_ratio(history, info),
        "5-Year Dividend Growth Rate (%)": calculate_dividend_growth_rate(history),
        "5-Year Earnings Growth (%)": calculate_earnings_growth(history),
        "Current Debt-to-Equity Ratio": info.get("debtToEquity", 0) / 100,
        "5-Year EPS Growth Rate (%)": calculate_eps_growth(symbol),
        "Dividend Age (Years)": calculate_dividend_age(history)
    }
    return conditions

def get_condition_color(condition, value):
    thresholds = {
        "Dividend Yield (%)": (3, ">"),
        "Payout Ratio (%)": (80, "<"),
        "5-Year Dividend Growth Rate (%)": (5, ">"),
        "5-Year Earnings Growth (%)": (5, ">"),
        "Current Debt-to-Equity Ratio": (0.5, "<"),
        "5-Year EPS Growth Rate (%)": (5, ">"),
        "Dividend Age (Years)": (10, ">")
    }
    
    threshold, comparison = thresholds.get(condition, (0, ">"))
    
    if threshold == 0:
        score = 1 if (comparison == ">" and value > 0) or (comparison == "<" and value < 0) else -1
    else:
        score = (value - threshold) / abs(threshold) if comparison == ">" else (threshold - value) / abs(threshold)
    
    score = max(-1, min(1, score))
    cmap = LinearSegmentedColormap.from_list("", ["red", "yellow", "green"])
    return cmap((score + 1) / 2)

def detect_missing_dividends(history):
    if history is None or history.empty or "Dividends" not in history.columns:
        return pd.DataFrame()

    dividend_dates = history[history["Dividends"] > 0].index
    if len(dividend_dates) < 2:
        return pd.DataFrame()

    avg_interval = (dividend_dates[-1] - dividend_dates[0]) / (len(dividend_dates) - 1)
    expected_dates = pd.date_range(start=dividend_dates[0], end=dividend_dates[-1], freq=avg_interval)
    
    missing_dividends = []
    for date in expected_dates:
        if date not in dividend_dates:
            nearest_actual = min(dividend_dates, key=lambda x: abs(x - date))
            if abs(nearest_actual - date) > timedelta(days=30):
                missing_dividends.append(date)

    return pd.DataFrame({"Date": missing_dividends, "Missed": True})

def visualize_stock_data(symbol, history, conditions, missing_dividends):
    if history is None or history.empty:
        print(f"No data available for {symbol}. Unable to visualize.")
        return

    fig = plt.figure(figsize=(20, 25))
    gs = GridSpec(5, 3, figure=fig)

    # Stock price chart
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(history.index, history["Close"])
    ax1.set_title(f"{symbol} Stock Price (Last 5 Years)")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Price")

    # Dividend chart
    ax2 = fig.add_subplot(gs[1, :])
    ax2.bar(history.index, history["Dividends"], color="blue", label="Paid Dividends")
    if not missing_dividends.empty:
        ax2.scatter(missing_dividends["Date"], [0] * len(missing_dividends), color="red", marker="x", s=100, label="Missing Dividends")
    ax2.set_title(f"{symbol} Dividends (Last 5 Years)")
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Dividend Amount")
    ax2.legend()

    # Conditions chart
    ax3 = fig.add_subplot(gs[2, :])
    conditions_df = pd.DataFrame.from_dict(conditions, orient="index", columns=["Value"])
    colors = [get_condition_color(cond, val) for cond, val in conditions_df["Value"].items()]
    
    conditions_df["Value"].plot(kind="bar", ax=ax3, color=colors)
    ax3.set_title("Stock Conditions (5-Year, Current, or All-Time)")
    ax3.set_xlabel("Metrics")
    ax3.set_ylabel("Value")
    ax3.tick_params(axis='x', rotation=45)

    for i, v in enumerate(conditions_df["Value"]):
        ax3.text(i, v, f"{v:.2f}", ha="center", va="bottom", color="black")

    # Conditions summary
    ax4 = fig.add_subplot(gs[3, :])
    ax4.axis("off")
    conditions_summary = "\n".join([f"{cond}: {val:.2f}" for cond, val in conditions_df["Value"].items()])
    ax4.text(0.5, 1, "Conditions Summary (5-Year, Current, or All-Time)", ha="center", va="top", fontsize=14, fontweight="bold")
    ax4.text(0.5, 0.9, conditions_summary, ha="center", va="top", fontsize=12)

    plt.tight_layout()
    plt.show()

def main():
    symbol = input("Enter a stock symbol: ")
    history, info = fetch_stock_data(symbol)
    
    if history is None or info is None: 
        print(f"Unable to fetch data for {symbol}. Please try again later or with a different symbol.")
        return

    conditions = check_conditions(symbol, history, info)
    missing_dividends = detect_missing_dividends(history)
    
    print(f"\nConditions for {symbol}:")
    for condition, value in conditions.items():
        print(f"{condition}: {value:.2f}")
    
    if not missing_dividends.empty:
        print("\nMissing Dividends:")
        for date in missing_dividends["Date"]:
            print(date.strftime("%Y-%m-%d"))
    else:
        print("\nNo missing dividends detected.")
    
    print("\nAnnual Dividend Data:")
    annual_dividends = history["Dividends"].groupby(history.index.year).sum()
    print(annual_dividends)
    
    visualize_stock_data(symbol, history, conditions, missing_dividends)

if __name__ == "__main__":
    main()
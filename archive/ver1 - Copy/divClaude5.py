import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime, timedelta
import math

## HELPER FUNCTIONS
def sigmoid(x):
    return 1 / (1 + math.exp(-x))

## DATA FETCH FUNCTIONS
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

def get_sp500_dividend_yield():
    try:
        history, info = fetch_stock_data("SPY", years=1)
        
        if history is None or history.empty:
            raise ValueError("No historical data available for SPY")
        
        total_dividends = history["Dividends"].sum()
        current_price = history["Close"].iloc[-1]
        
        dividend_yield = (total_dividends / current_price) * 100
        
        return dividend_yield
    except Exception as e:
        print(f"Error calculating S&P 500 dividend yield: {e}")
        return 2.0
    
##  METRICS FUNCTIONS
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

def calculate_dividend_value(dividend_yield, dividend_growth_rate):
    if dividend_growth_rate < 0:
        return -1
    # Cap the growth rate at the upper limit of 25%
    capped_growth_rate = min(dividend_growth_rate, 0.25)
    
    # Calculate the dividend_value
    dividend_value = dividend_yield * (1 + capped_growth_rate) ** 5
    
    return dividend_value
    
## VISUAL FUNCTIONS
def get_condition_color(score):
    cmap = LinearSegmentedColormap.from_list("", ["red", "yellow", "green"])
    return cmap(score)

def visualize_stock_data(symbol, history, conditions, raw_scores, initial_score, final_score, missing_dividends, thresholds, penalties):
    if history is None or history.empty:
        print(f"No data available for {symbol}. Unable to visualize.")
        return

    fig = plt.figure(figsize=(16, 14))
    gs = GridSpec(4, 3, figure=fig, height_ratios=[1, 1, 1, 0.5])

    # Stock price chart
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(history.index, history["Close"])
    ax1.set_title(f"{symbol} Stock Price (Last 5 Years)", fontsize=12)
    ax1.set_xlabel("Date", fontsize=10)
    ax1.set_ylabel("Price", fontsize=10)
    ax1.tick_params(axis='both', labelsize=8)

    # Dividend chart
    ax2 = fig.add_subplot(gs[1, :])
    
    dividend_dates = history[history["Dividends"] > 0].index
    dividend_amounts = history.loc[dividend_dates, "Dividends"]

    if not dividend_amounts.empty:
        # Plot individual dividend payments as sticks
        ax2.vlines(dividend_dates, ymin=0, ymax=dividend_amounts, color="blue", label="Dividends")
        ax2.set_ylabel("Dividend Amount", fontsize=10)
        ax2.set_ylim(0, max(dividend_amounts) * 1.1)
        
        # Highlight missing dividends
        if not missing_dividends.empty:
            ax2.scatter(missing_dividends["Date"], [0] * len(missing_dividends), color="red", marker="x", s=50, label="Missing Dividends")
        
        ax2.legend(fontsize=8, loc='upper left')
    else:
        ax2.text(0.5, 0.5, "No dividend data available", horizontalalignment='center', verticalalignment='center', transform=ax2.transAxes)

    ax2.set_title(f"{symbol} Dividends (Last 5 Years)", fontsize=12)
    ax2.set_xlabel("Date", fontsize=10)
    ax2.tick_params(axis='both', labelsize=8)

    # Conditions chart
    ax3 = fig.add_subplot(gs[2, :])
    conditions_df = pd.DataFrame.from_dict(conditions, orient="index", columns=["Value"])
    
    colors = [get_condition_color(raw_scores[condition]) for condition in conditions]
    
    conditions_df["Value"].plot(kind="bar", ax=ax3, color=colors)
    ax3.set_title(f"Stock Conditions and Raw Scores", fontsize=12)
    ax3.set_xlabel("Metrics", fontsize=10)
    ax3.set_ylabel("Value", fontsize=10)
    ax3.tick_params(axis='x', rotation=45, labelsize=8)
    ax3.tick_params(axis='y', labelsize=8)

    for i, (condition, value) in enumerate(conditions.items()):
        ax3.text(i, value + 0.05, f"{value:.2f}", ha="center", va="bottom", fontsize=8, color="black")
        ax3.text(i, -max(conditions_df["Value"]) * 0.05, f"Score: {raw_scores[condition]:.2f}", ha="center", va="top", fontsize=8, color="black")

    # Add a new subplot for the score breakdown
    ax4 = fig.add_subplot(gs[3, :])
    ax4.axis('off')
    ax4.text(0.5, 0.6, f"Initial Score: {initial_score:.2f}", ha='center', va='center', fontsize=12)
    ax4.text(0.5, 0.4, f"Penalties: {penalties:.2f}", ha='center', va='center', fontsize=12)
    ax4.text(0.5, 0.2, f"Final Score: {final_score:.2f}", ha='center', va='center', fontsize=12, fontweight='bold')

    plt.tight_layout()
    plt.show()
    
## SCORING FUNCTIONS
def payout_ratio_score(value, threshold):
    if value <= threshold:
        return 1 - 0.1 * (value / threshold)**2
    else:
        return 0.8 * math.exp(-2*((value - threshold) / threshold)**2)
    
def debt_to_equity_score(value, threshold):
    if value <= threshold:
        return 1 - 0.1 * (value / threshold)**2
    else:
        return 0.8 * math.exp(-2*((value - threshold) / threshold)**2)
    
def check_conditions(symbol, history, info):
    sp500_dividend_yield = get_sp500_dividend_yield()
    dividend_yield = calculate_dividend_yield(history, info)
    dividend_growth_rate = calculate_dividend_growth_rate(history)
    conditions = {
        "Dividend Value (%)": calculate_dividend_value(dividend_yield, dividend_growth_rate),
        # "Dividend Yield (%)": calculate_dividend_yield(history, info),
        "Payout Ratio (%)": calculate_payout_ratio(history, info),
        # "5-Year Dividend Growth Rate (%)": calculate_dividend_growth_rate(history),
        "5-Year Earnings Growth (%)": calculate_earnings_growth(history),
        "Current Debt-to-Equity Ratio": info.get("debtToEquity", 300) / 100,
        "5-Year EPS Growth Rate (%)": calculate_eps_growth(symbol),
        "Dividend Age (Years)": calculate_dividend_age(history)
    }
    
    weights = {
        "Dividend Value (%)": 0.4,
        "Payout Ratio (%)": 0.15,
        # "5-Year Dividend Growth Rate (%)": 0.15,
        "5-Year Earnings Growth (%)": 0.15,
        "Current Debt-to-Equity Ratio": 0.10,
        "5-Year EPS Growth Rate (%)": 0.10,
        "Dividend Age (Years)": 0.10
    }
    
    thresholds = {
        "Dividend Value (%)": (sp500_dividend_yield, ">"),
        "Payout Ratio (%)": (50, "<"),
        # "5-Year Dividend Growth Rate (%)": (10, ">"),
        "5-Year Earnings Growth (%)": (5, ">"),
        "Current Debt-to-Equity Ratio": (0.5, "<"),
        "5-Year EPS Growth Rate (%)": (5, ">"),
        "Dividend Age (Years)": (7, ">")
    }
    
    raw_scores = {}
    for condition, value in conditions.items():
        threshold, comparison = thresholds[condition]
        
        # if condition == "Dividend Yield (%)":
        #     score = max(-0.5, 1 - math.exp(-value / threshold))
        if condition == "Dividend Value (%)":
            score = max(-0.5, 1 - math.exp(-value / threshold))
        elif condition == "Payout Ratio (%)":
            score = max(-0.5, payout_ratio_score(value, threshold))
        # elif condition == "5-Year Dividend Growth Rate (%)":
        #     score = max(-0.5, 1 - math.exp(-value / threshold))
        elif condition == "Current Debt-to-Equity Ratio":
            score = max(-0.5, debt_to_equity_score(value, threshold))
        elif condition == "Dividend Age (Years)":
            score = max(-0.5, 1 - math.exp(-value / threshold))
        else:
            if comparison == ">":
                score = max(-0.5, 1 - math.exp(-value / threshold))
            else:
                score = max(-0.5, math.exp(-value / threshold))
        
        raw_scores[condition] = score
    
    initial_score = sum(raw_scores[condition] * weights[condition] for condition in conditions)
    
    # Apply penalties
    penalties = 0
    if not (0.8 * sp500_dividend_yield < dividend_yield < 8):
        penalties += 0.1
    if conditions["Payout Ratio (%)"] >= 80:
        penalties += 0.1
    if not (5 < dividend_growth_rate < 25):
        penalties += 0.1
    if conditions["5-Year Earnings Growth (%)"] <= 3:  # Updated condition
        penalties += 0.1
    if conditions["5-Year Earnings Growth (%)"] > 25:  # Updated condition
        penalties += 0.1/2
    if conditions["Current Debt-to-Equity Ratio"] >= 2:  # Updated condition
        penalties += 0.1
    if conditions["5-Year EPS Growth Rate (%)"] <= 3:  # Updated condition
        penalties += 0.1
    if conditions["5-Year EPS Growth Rate (%)"] > 25:  # Updated condition
        penalties += 0.1/2
    if conditions["Dividend Age (Years)"] <= 5:
        penalties += 0.1
        
    # Reduce penalties
    if(dividend_yield > 2 * sp500_dividend_yield):
        penalties -= 0.1
    
    final_score = max(0, initial_score - penalties)
    
    return conditions, raw_scores, initial_score, final_score, thresholds, penalties, weights

## MAIN FUNCTION
def main():
    symbol = input("Enter a stock symbol: ")
    history, info = fetch_stock_data(symbol)
    
    if history is None or info is None: 
        print(f"Unable to fetch data for {symbol}. Please try again later or with a different symbol.")
        return

    conditions, raw_scores, initial_score, final_score, thresholds, penalties, weights = check_conditions(symbol, history, info)
    missing_dividends = detect_missing_dividends(history)
    
    print(f"\nConditions for {symbol}:")
    for condition, value in conditions.items():
        print(f"{condition}: {value:.2f}")
    
    print("\nRaw Scores:")
    for condition, score in raw_scores.items():
        print(f"{condition}: {score:.2f}")
    
    print(f"\nInitial Score: {initial_score:.2f}")
    print(f"Penalties: {penalties:.2f}")
    print(f"Final Score: {final_score:.2f}")
    
    if not missing_dividends.empty:
        print("\nMissing Dividends:")
        for date in missing_dividends["Date"]:
            print(date.strftime("%Y-%m-%d"))
    else:
        print("\nNo missing dividends detected.")
    
    print("\nAnnual Dividend Data:")
    annual_dividends = history["Dividends"].groupby(history.index.year).sum()
    print(annual_dividends)
    
    visualize_stock_data(symbol, history, conditions, raw_scores, initial_score, final_score, missing_dividends, thresholds, penalties)

if __name__ == "__main__":
    main()
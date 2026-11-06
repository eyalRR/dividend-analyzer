from flask import Flask, request, jsonify
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math

app = Flask(__name__)
CORS(app)

def fetch_stock_data(symbol, years=10):
    try:
        stock = yf.Ticker(symbol)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        history = stock.history(start=start_date, end=end_date)
        info = stock.info
        
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
        info = stock.info
        
        if 'trailingEps' not in info:
            print(f"Trailing EPS not found for {symbol}. Skipping EPS growth calculation.")
            return 0
        
        current_eps = info['trailingEps']
        
        start_date = (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        history = stock.history(start=start_date, end=end_date)
        
        if history.empty:
            print(f"No historical data available for {symbol} in the past 5 years.")
            return 0
        
        past_close = history['Close'].iloc[0]
        past_eps = past_close * current_eps / info['previousClose']
        
        eps_growth = (current_eps / past_eps) ** (1/5) - 1
        eps_growth_rate = eps_growth * 100
        
        return eps_growth_rate
    except Exception as e:
        print(f"Error calculating EPS growth for {symbol}: {e}")
        return 0

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
    conditions = {
        "Dividend Yield (%)": calculate_dividend_yield(history, info),
        "Payout Ratio (%)": calculate_payout_ratio(history, info),
        "5-Year Dividend Growth Rate (%)": calculate_dividend_growth_rate(history),
        "5-Year Earnings Growth (%)": calculate_earnings_growth(history),
        "Current Debt-to-Equity Ratio": info.get("debtToEquity", 300) / 100,
        "5-Year EPS Growth Rate (%)": calculate_eps_growth(symbol),
        "Dividend Age (Years)": calculate_dividend_age(history)
    }
    
    weights = {
        "Dividend Yield (%)": 0.25,
        "Payout Ratio (%)": 0.15,
        "5-Year Dividend Growth Rate (%)": 0.15,
        "5-Year Earnings Growth (%)": 0.15,
        "Current Debt-to-Equity Ratio": 0.10,
        "5-Year EPS Growth Rate (%)": 0.10,
        "Dividend Age (Years)": 0.10
    }
    
    thresholds = {
        "Dividend Yield (%)": (sp500_dividend_yield, ">"),
        "Payout Ratio (%)": (50, "<"),
        "5-Year Dividend Growth Rate (%)": (10, ">"),
        "5-Year Earnings Growth (%)": (5, ">"),
        "Current Debt-to-Equity Ratio": (0.5, "<"),
        "5-Year EPS Growth Rate (%)": (5, ">"),
        "Dividend Age (Years)": (7, ">")
    }
    
    raw_scores = {}
    for condition, value in conditions.items():
        threshold, comparison = thresholds[condition]
        
        if condition == "Dividend Yield (%)":
            score = max(-0.5, 1 - math.exp(-value / threshold))
        elif condition == "Payout Ratio (%)":
            score = max(-0.5, payout_ratio_score(value, threshold))
        elif condition == "5-Year Dividend Growth Rate (%)":
            score = max(-0.5, 1 - math.exp(-value / threshold))
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
    
    penalties = 0
    if not (0.8 * sp500_dividend_yield < conditions["Dividend Yield (%)"] < 8):
        penalties += 0.1
    if conditions["Payout Ratio (%)"] >= 80:
        penalties += 0.1
    if not (5 < conditions["5-Year Dividend Growth Rate (%)"] < 25):
        penalties += 0.1
    if conditions["5-Year Earnings Growth (%)"] <= 3:
        penalties += 0.1
    if conditions["5-Year Earnings Growth (%)"] > 25:
        penalties += 0.1/2
    if conditions["Current Debt-to-Equity Ratio"] >= 2:
        penalties += 0.1
    if conditions["5-Year EPS Growth Rate (%)"] <= 3:
        penalties += 0.1
    if conditions["5-Year EPS Growth Rate (%)"] > 25:
        penalties += 0.1/2
    if conditions["Dividend Age (Years)"] <= 5:
        penalties += 0.1
    
    final_score = max(0, initial_score - penalties)
    
    return conditions, raw_scores, initial_score, final_score, thresholds, penalties, weights

def detect_missing_dividends(history):
    if history is None or history.empty or "Dividends" not in history.columns:
        return []

    dividend_dates = history[history["Dividends"] > 0].index
    if len(dividend_dates) < 2:
        return []

    avg_interval = (dividend_dates[-1] - dividend_dates[0]) / (len(dividend_dates) - 1)
    expected_dates = pd.date_range(start=dividend_dates[0], end=dividend_dates[-1], freq=avg_interval)
    
    missing_dividends = []
    for date in expected_dates:
        if date not in dividend_dates:
            nearest_actual = min(dividend_dates, key=lambda x: abs(x - date))
            if abs(nearest_actual - date) > timedelta(days=30):
                missing_dividends.append(date.strftime("%Y-%m-%d"))

    return missing_dividends

@app.route('/analyze', methods=['POST'])
def analyze_stock():
    data = request.json
    symbol = data.get('symbol')
    
    if not symbol:
        return jsonify({"error": "No stock symbol provided"}), 400
    
    history, info = fetch_stock_data(symbol)
    
    if history is None or info is None:
        return jsonify({"error": f"Unable to fetch data for {symbol}"}), 404

    conditions, raw_scores, initial_score, final_score, thresholds, penalties, weights = check_conditions(symbol, history, info)
    missing_dividends = detect_missing_dividends(history)
    
    annual_dividends = history["Dividends"].groupby(history.index.year).sum().to_dict()
    
    result = {
        "symbol": symbol,
        "conditions": conditions,
        "raw_scores": raw_scores,
        "initial_score": initial_score,
        "final_score": final_score,
        "thresholds": thresholds,
        "penalties": penalties,
        "weights": weights,
        "missing_dividends": missing_dividends,
        "annual_dividends": annual_dividends
    }
    
    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True)
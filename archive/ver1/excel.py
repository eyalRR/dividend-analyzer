import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math
from openpyxl import load_workbook

def fetch_stock_data(symbol, years=10):
    """
    Fetches historical stock data from Yahoo Finance.

    Args:
        symbol (str): The stock symbol.
        years (int): The number of years of historical data to fetch.

    Returns:
        tuple: A tuple containing the historical data (DataFrame) and stock info (dict).
    """
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
    """
    Calculates the dividend growth rate.

    Args:
        history (pd.DataFrame): The historical stock data.

    Returns:
        float: The dividend growth rate as a percentage.
    """
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
    """
    Calculates the earnings growth rate.

    Args:
        history (pd.DataFrame): The historical stock data.

    Returns:
        float: The earnings growth rate as a percentage.
    """
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
    """
    Calculates the dividend yield.

    Args:
        history (pd.DataFrame): The historical stock data.
        info (dict): Stock information.

    Returns:
        float: The dividend yield as a percentage.
    """
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
    """
    Calculates the payout ratio.

    Args:
        history (pd.DataFrame): The historical stock data.
        info (dict): Stock information.

    Returns:
        float: The payout ratio as a percentage.
    """
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
    """
    Calculates the dividend age.

    Args:
        history (pd.DataFrame): The historical stock data.

    Returns:
        float: The dividend age in years.
    """
    if history is None or history.empty or "Dividends" not in history.columns:
        return 0
    
    dividend_dates = history[history["Dividends"] > 0].index
    if len(dividend_dates) == 0:
        return 0
    
    first_dividend_date = dividend_dates.min()
    dividend_age = (datetime.now() - first_dividend_date).days / 365.25
    
    return round(dividend_age, 2)

def calculate_eps_growth(symbol):
    """
    Calculates the EPS growth rate.

    Args:
        symbol (str): The stock symbol.

    Returns:
        float: The EPS growth rate as a percentage.
    """
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
    
def calculate_dividend_value(dividend_yield, dividend_growth_rate):
    """
    Calculates the dividend value.

    Args:
        dividend_yield (float): The dividend yield as a percentage.
        dividend_growth_rate (float): The dividend growth rate as a percentage.

    Returns:
        float: The calculated dividend value.
    """
    if dividend_growth_rate < 0:
        return -1
    # Cap the growth rate at the upper limit of 25%
    capped_growth_rate = min(dividend_growth_rate, 0.25)
    
    # Calculate the dividend_value
    dividend_value = dividend_yield * (1 + capped_growth_rate) ** 5
    
    return dividend_value

def get_sp500_dividend_yield():
    """
    Gets the S&P 500 dividend yield.

    Returns:
        float: The S&P 500 dividend yield as a percentage.
    """
    try:
        history, info = fetch_stock_data("SPY", years=1)
        
        if history is None or history.empty:
            raise ValueError("No historical data available for SPY")
        
        total_dividends = history["Dividends"].sum()
        
        current_price = history["Close"].iloc[-1]
        
        dividend_yield = (total_dividends / current_price) * 100
        
        print(f"Calculated S&P 500 dividend yield: {dividend_yield:.2f}%")
        return dividend_yield
    except Exception as e:
        print(f"Error calculating S&P 500 dividend yield: {e}")
        print("Using default value of 2%")
        return 2.0

def payout_ratio_score(value, threshold):
    """
    Calculates a score based on the payout ratio.

    Args:
        value (float): The payout ratio value.
        threshold (float): The threshold value.

    Returns:
        float: The calculated score.
    """
    if value <= threshold:
        return 1 - 0.1 * (value / threshold)**2
    else:
        return 0.8 * math.exp(-2*((value - threshold) / threshold)**2)

def debt_to_equity_score(value, threshold):
    """
    Calculates a score based on the debt-to-equity ratio.

    Args:
        value (float): The debt-to-equity ratio value.
        threshold (float): The threshold value.

    Returns:
        float: The calculated score.
    """
    if value <= threshold:
        return 1 - 0.1 * (value / threshold)**2
    else:
        return 0.8 * math.exp(-2*((value - threshold) / threshold)**2)

def check_conditions(symbol, history, info, sp500_dividend_yield):
    """
    Checks various conditions for a given stock and calculates a final score.

    Args:
        symbol (str): The stock symbol.
        history (pd.DataFrame): The historical stock data.
        info (dict): Stock information.
        sp500_dividend_yield (float): The S&P 500 dividend yield.

    Returns:
        tuple: A tuple containing conditions, raw scores, initial score, final score, thresholds, penalties, and weights.
    """
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
    
    penalties = 0
    if not (0.8 * sp500_dividend_yield < dividend_yield < 8):
        penalties += 0.1
    if conditions["Payout Ratio (%)"] >= 80:
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

def read_excel_symbols(file_path, sheet_name):
    """
    Reads stock symbols from an Excel file.

    Args:
        file_path (str): The path to the Excel file.
        sheet_name (str): The name of the sheet containing the symbols.

    Returns:
        list: A list of stock symbols.
    """
    wb = load_workbook(file_path)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found in the Excel file.")
    ws = wb[sheet_name]
    symbols = [cell.value for cell in ws['A'][1:] if cell.value]  # Assuming symbols are in column A
    return symbols

def update_excel_with_results(file_path, sheet_name, results):
    """
    Updates an Excel file with stock analysis results.

    Args:
        file_path (str): The path to the Excel file.
        sheet_name (str): The name of the sheet to update.
        results (list): A list of tuples containing (symbol, score, date).
    """
    wb = load_workbook(file_path)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found in the Excel file.")
    ws = wb[sheet_name]
    
    # Find the last row with data in column A
    last_row = ws.max_row
    while last_row > 1 and ws.cell(row=last_row, column=1).value is None:
        last_row -= 1
    
    # Create a dictionary to map symbols to their scores and dates
    result_dict = {symbol: (score, date) for symbol, score, date in results}
    
    # Update scores and dates for existing symbols
    for row in range(2, last_row + 1):  # Assuming row 1 is header
        symbol = ws.cell(row=row, column=1).value
        if symbol in result_dict:
            score, date = result_dict[symbol]
            ws.cell(row=row, column=2, value=score)
            ws.cell(row=row, column=3, value=date)
            del result_dict[symbol]  # Remove processed symbol from dict
    
    # Add any remaining new symbols
    row = last_row + 1
    for symbol, (score, date) in result_dict.items():
        ws.cell(row=row, column=1, value=symbol)
        ws.cell(row=row, column=2, value=score)
        ws.cell(row=row, column=3, value=date)
        row += 1
    
    wb.save(file_path)

def process_symbol(symbol, sp500_dividend_yield):
    """
    Processes a single stock symbol to calculate its final score.

    Args:
        symbol (str): The stock symbol.
        sp500_dividend_yield (float): The S&P 500 dividend yield.

    Returns:
        tuple: A tuple containing the symbol, final score, and current date.
    """
    history, info = fetch_stock_data(symbol)
    
    if history is None or info is None: 
        print(f"Unable to fetch data for {symbol}. Skipping.")
        return None

    conditions, raw_scores, initial_score, final_score, thresholds, penalties, weights = check_conditions(symbol, history, info, sp500_dividend_yield)
    
    print(f"\nResults for {symbol}:")
    print(f"Final Score: {final_score:.2f}")
    print(f"Date: {datetime.now().date()}")
    
    return (symbol, final_score, datetime.now().date())

def main():
    """
    Main function to execute the dividend analysis process.
    Prompts the user for the Excel file path and sheet name,
    reads stock symbols, processes each symbol, and updates the Excel file with the results.
    """
    excel_file = input("Enter the path to your Excel file: ")
    
    while True:
        sheet_name = input("Enter the sheet name ('onezero' or 'pepper' or 'spy' or 'nyse'): ").lower()
        if sheet_name in ['onezero', 'pepper', 'spy', 'nyse']:
            break
        else:
            print("Invalid sheet name. Please enter 'onezero' or 'pepper' or 'spy' or 'nyse'.")
    
    try:
        symbols = read_excel_symbols(excel_file, sheet_name)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return
    
    results = []
    sp500_dividend_yield = get_sp500_dividend_yield()
    for symbol in symbols:
        result = process_symbol(symbol, sp500_dividend_yield)
        if result:
            results.append(result)
    
    try:
        update_excel_with_results(excel_file, sheet_name, results)
        print(f"\nResults have been written to {excel_file} in sheet '{sheet_name}'")
    except Exception as e:
        print(f"Error writing to Excel file: {e}")

if __name__ == "__main__":
    main()

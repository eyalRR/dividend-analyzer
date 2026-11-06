import pandas as pd
import requests
from datetime import datetime

def analyze_stock(symbol):
    url = "http://localhost:5000/analyze"
    payload = {"symbol": symbol}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as err:
        print(f"An error occurred while analyzing {symbol}: {err}")
        return None

def update_sheet(df, sheet_name):
    for index, row in df.iterrows():
        symbol = row['symbol']
        if pd.notnull(symbol) and symbol.strip() != '':
            result = analyze_stock(symbol)
            if result:
                df.at[index, 'score'] = result['final_score']
                df.at[index, 'date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"Updated {symbol} in sheet {sheet_name}: Score = {result['final_score']:.2f}")
            else:
                print(f"Failed to update {symbol} in sheet {sheet_name}")
        else:
            print(f"Skipping empty or invalid symbol at row {index + 2} in sheet {sheet_name}")
    return df

def update_excel_with_api_results(file_path, sheet_name=None):
    xls = pd.ExcelFile(file_path)
    sheet_names = xls.sheet_names

    if sheet_name and sheet_name not in sheet_names:
        print(f"Sheet '{sheet_name}' not found in the Excel file.")
        return

    writer = pd.ExcelWriter(file_path, engine='openpyxl')

    for sn in sheet_names:
        df = pd.read_excel(xls, sheet_name=sn)
        
        for col in ['symbol', 'score', 'date']:
            if col not in df.columns:
                df[col] = None if col != 'symbol' else ''
        
        if not sheet_name or sn == sheet_name:
            df = update_sheet(df, sn)
        
        df.to_excel(writer, sheet_name=sn, index=False)

    writer.save()
    print(f"Excel file updated: {file_path}")

def display_single_stock_analysis(symbol):
    result = analyze_stock(symbol)
    if result:
        print(f"\nAnalysis for {symbol}:")
        print(f"Final Score: {result['final_score']:.2f}")
        print("\nConditions:")
        for condition, value in result['conditions'].items():
            print(f"  {condition}: {value:.2f}")
        print(f"\nMissing Dividends: {', '.join(result['missing_dividends']) if result['missing_dividends'] else 'None'}")
        print("\nAnnual Dividends:")
        for year, dividend in sorted(result['annual_dividends'].items()):
            print(f"  {year}: {dividend:.2f}")
    else:
        print(f"Failed to analyze {symbol}")

if __name__ == "__main__":
    choice = input("Do you want to update the Excel file (E) or analyze a single stock (S)? ").strip().upper()
    
    if choice == 'E':
        file_path = input("Enter the path to your Excel file: ")
        sheet_name = input("Enter the sheet name (leave blank for all sheets): ").strip()
        update_excel_with_api_results(file_path, sheet_name if sheet_name else None)
    elif choice == 'S':
        symbol = input("Enter the stock symbol to analyze: ").strip().upper()
        display_single_stock_analysis(symbol)
    else:
        print("Invalid choice. Please run the script again and choose 'E' or 'S'.")
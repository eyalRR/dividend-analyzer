import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from tkinter import *
from tkinter import messagebox

def get_dividend_buyback_data():
    stock_symbol = stock_symbol_entry.get()
    try:
        stock = yf.Ticker(stock_symbol)
        dividends = stock.dividends.to_frame()
        buybacks = stock.splits.to_frame()
        df = pd.concat([dividends, buybacks], axis=1)
        df.columns = ['Dividends', 'Buybacks']
        df['Year'] = df.index.year
        df = df.groupby('Year').sum()
        return df
    except:
        messagebox.showerror("Error", "Invalid Stock Symbol")

def plot_graph():
    df = get_dividend_buyback_data()
    if df is not None:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(df.index, df['Dividends'], color='blue', label='Dividends')
        ax.bar(df.index, df['Buybacks'], color='red', label='Buybacks')
        ax.set_xlabel('Year')
        ax.set_ylabel('Amount per Share')
        ax.set_title('Dividends and Buybacks per Share for {}'.format(stock_symbol_entry.get()))
        ax.legend()
        plt.show()

root = Tk()
root.title("Stock Dividends and Buybacks Data")
root.geometry("400x200")

stock_symbol_label = Label(root, text="Enter Stock Symbol")
stock_symbol_label.pack()

stock_symbol_entry = Entry(root)
stock_symbol_entry.pack()

plot_button = Button(root, text="Plot Graph", command=plot_graph)
plot_button.pack()

root.mainloop()
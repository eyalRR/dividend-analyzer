"""Excel batch processing module for reading portfolios and writing dividend analysis scores.
"""
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
from datetime import datetime
import openpyxl
import pandas as pd
from dividend_analyzer.data.fetcher import DataFetcher
from dividend_analyzer.algorithms.factory import get_algorithm
from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.models import StockAnalysisResult

class ExcelBatchProcessor:
    """Processes Excel files containing stock symbols and writes analysis scores back to sheets."""

    def __init__(
        self,
        fetcher: Optional[DataFetcher] = None,
        default_version: AlgorithmVersion = AlgorithmVersion.V5_DIVIDEND_VALUE,
    ):
        self.fetcher = fetcher or DataFetcher()
        self.default_version = default_version

    def get_sheet_names(self, file_path: str | Path) -> List[str]:
        wb = openpyxl.load_workbook(file_path, read_only=True)
        sheet_names = list(wb.sheetnames)
        wb.close()
        return sheet_names

    def process_file(
        self,
        file_path: str | Path,
        sheet_name: Optional[str] = None,
        version: Optional[AlgorithmVersion] = None,
        progress_callback: Optional[Callable[[int, int, str, Optional[StockAnalysisResult]], None]] = None,
    ) -> Dict[str, List[StockAnalysisResult]]:
        """Process stock symbols in an Excel file and save updated scores and dates.
        Returns a dictionary mapping sheet names to lists of analysis results.
        """
        algo_version = version or self.default_version
        algo = get_algorithm(algo_version)
        benchmark_yield = self.fetcher.get_benchmark_dividend_yield()

        wb = openpyxl.load_workbook(file_path)
        target_sheets = [sheet_name] if sheet_name else wb.sheetnames

        results_by_sheet = {}

        for sn in target_sheets:
            if sn not in wb.sheetnames:
                continue

            ws = wb[sn]
            # Identify columns
            header_map = {}
            for col in range(1, ws.max_column + 1):
                val = ws.cell(row=1, column=col).value
                if val:
                    header_map[str(val).strip().lower()] = col

            # Find symbol column
            symbol_col = (
                header_map.get("symbol")
                or header_map.get("ticker")
                or 1
            )

            # Ensure score and date headers exist
            score_col = header_map.get("score")
            if not score_col:
                score_col = ws.max_column + 1
                ws.cell(row=1, column=score_col, value="score")
                header_map["score"] = score_col

            date_col = header_map.get("date")
            if not date_col:
                date_col = ws.max_column + 1
                ws.cell(row=1, column=date_col, value="date")
                header_map["date"] = date_col

            # Gather symbols
            rows_to_process = []
            for r in range(2, ws.max_row + 1):
                sym = ws.cell(row=r, column=symbol_col).value
                if sym and str(sym).strip():
                    clean_sym = str(sym).strip().upper()
                    # Skip common header repetitions or notes
                    if clean_sym not in ["SYMBOL", "TICKER", "COMPANY"]:
                        rows_to_process.append((r, clean_sym))

            total_items = len(rows_to_process)
            sheet_results = []

            for idx, (row_idx, sym) in enumerate(rows_to_process, start=1):
                res = None
                try:
                    history, info = self.fetcher.fetch_stock_data(sym)
                    if history is not None and info:
                        res = algo.analyze(sym, history, info, benchmark_yield)
                        ws.cell(row=row_idx, column=score_col, value=res.final_score)
                        ws.cell(
                            row=row_idx,
                            column=date_col,
                            value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        )
                        sheet_results.append(res)
                except Exception as e:
                    print(f"Error processing {sym}: {e}")

                if progress_callback:
                    progress_callback(idx, total_items, sym, res)

            results_by_sheet[sn] = sheet_results

        wb.save(file_path)
        return results_by_sheet

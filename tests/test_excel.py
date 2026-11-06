"""Unit tests verifying Excel batch read and write operations.
"""
import openpyxl
from dividend_analyzer.excel.processor import ExcelBatchProcessor
from dividend_analyzer.algorithms.versions import AlgorithmVersion

class MockFetcher:
    """Mock data fetcher returning synthetic data without network calls."""
    def __init__(self, sample_data):
        self.history, self.info = sample_data

    def fetch_stock_data(self, symbol, years=10):
        return self.history, self.info

    def get_benchmark_dividend_yield(self, symbol="SPY"):
        return 1.5

def test_excel_batch_processor(tmp_path, sample_stock_data):
    excel_path = tmp_path / "test_portfolio.xlsx"

    # Create test workbook with a 'symbols' column
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "test_sheet"
    ws.append(["symbol", "company"])
    ws.append(["AAPL", "Apple Inc."])
    ws.append(["MSFT", "Microsoft Corp."])
    wb.save(excel_path)

    mock_fetcher = MockFetcher(sample_stock_data)
    processor = ExcelBatchProcessor(fetcher=mock_fetcher, default_version=AlgorithmVersion.V5_DIVIDEND_VALUE)

    results = processor.process_file(excel_path, sheet_name="test_sheet")

    assert "test_sheet" in results
    assert len(results["test_sheet"]) == 2

    # Verify that the workbook was updated with score and date columns
    updated_wb = openpyxl.load_workbook(excel_path)
    updated_ws = updated_wb["test_sheet"]

    headers = [updated_ws.cell(row=1, column=c).value for c in range(1, updated_ws.max_column + 1)]
    assert "score" in headers
    assert "date" in headers

    score_val = updated_ws.cell(row=2, column=headers.index("score") + 1).value
    assert score_val is not None
    assert isinstance(score_val, (int, float))

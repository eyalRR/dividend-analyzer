"""Persistent SQLite cache layer for stock fundamental and historical price data.
Reduces network round-trips and protects against Yahoo Finance rate limiting.
"""
import sqlite3
import json
import pickle
import time
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
from dividend_analyzer.config import (
    DEFAULT_CACHE_DB,
    CACHE_INFO_TTL,
    CACHE_HISTORY_TTL,
    CACHE_BENCHMARK_TTL,
)

class DataCache:
    """SQLite-backed caching layer for ticker fundamentals and price/dividend histories."""

    def __init__(self, db_path: Path = DEFAULT_CACHE_DB):
        self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS info_cache (
                    symbol TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history_cache (
                    symbol TEXT,
                    years INTEGER,
                    data BLOB NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (symbol, years)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_cache (
                    symbol TEXT PRIMARY KEY,
                    dividend_yield REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()

    def get_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        symbol = symbol.upper()
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data, updated_at FROM info_cache WHERE symbol = ?",
                (symbol,)
            )
            row = cursor.fetchone()
            if row and (now - row["updated_at"]) < CACHE_INFO_TTL:
                try:
                    return json.loads(row["data"])
                except Exception:
                    return None
        return None

    def set_info(self, symbol: str, info: Dict[str, Any]) -> None:
        symbol = symbol.upper()
        now = time.time()
        # Clean non-serializable fields if any
        clean_info = {}
        for k, v in info.items():
            if isinstance(v, (str, int, float, bool, list, dict, type(None))):
                clean_info[k] = v
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO info_cache (symbol, data, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (symbol, json.dumps(clean_info), now)
            )
            conn.commit()

    def get_history(self, symbol: str, years: int) -> Optional[pd.DataFrame]:
        symbol = symbol.upper()
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data, updated_at FROM history_cache WHERE symbol = ? AND years = ?",
                (symbol, years)
            )
            row = cursor.fetchone()
            if row and (now - row["updated_at"]) < CACHE_HISTORY_TTL:
                try:
                    return pickle.loads(row["data"])
                except Exception:
                    return None
        return None

    def set_history(self, symbol: str, years: int, df: pd.DataFrame) -> None:
        symbol = symbol.upper()
        now = time.time()
        try:
            blob = pickle.dumps(df)
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO history_cache (symbol, years, data, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(symbol, years) DO UPDATE SET
                        data = excluded.data,
                        updated_at = excluded.updated_at
                    """,
                    (symbol, years, blob, now)
                )
                conn.commit()
        except Exception:
            pass

    def get_benchmark(self, symbol: str) -> Optional[float]:
        symbol = symbol.upper()
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT dividend_yield, updated_at FROM benchmark_cache WHERE symbol = ?",
                (symbol,)
            )
            row = cursor.fetchone()
            if row and (now - row["updated_at"]) < CACHE_BENCHMARK_TTL:
                return float(row["dividend_yield"])
        return None

    def set_benchmark(self, symbol: str, dividend_yield: float) -> None:
        symbol = symbol.upper()
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO benchmark_cache (symbol, dividend_yield, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    dividend_yield = excluded.dividend_yield,
                    updated_at = excluded.updated_at
                """,
                (symbol, float(dividend_yield), now)
            )
            conn.commit()

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM info_cache")
            conn.execute("DELETE FROM history_cache")
            conn.execute("DELETE FROM benchmark_cache")
            conn.commit()

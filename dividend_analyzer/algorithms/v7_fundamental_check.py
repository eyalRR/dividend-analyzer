"""Version 7: Fundamental Check -- wraps the vendored fundamental-check skill's
Quality/Risk gauntlet (profitability, cash generation, leverage, liquidity,
dilution, earnings quality, hard AVOID gate) as a pipeline algorithm.

Unlike V1-V6, this version does not score off the history/info the pipeline
already fetched -- fundamental_check.py is a self-contained, deterministic
tool that always fetches its own fresh data (about 10 yfinance calls per
symbol) via its own subprocess, by design (a pre-trade sanity check wants
current data, not whatever happens to be in the SQLite cache). It is
therefore much slower per symbol than the other six versions.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple, Any

import pandas as pd
from dividend_analyzer.algorithms.base import BaseAlgorithm
from dividend_analyzer.algorithms.versions import AlgorithmVersion

REPO_ROOT = Path(__file__).resolve().parents[2]
FUNDAMENTAL_CHECK = REPO_ROOT / ".claude" / "skills" / "fundamental-check" / "fundamental_check.py"

QUALITY_THRESHOLD = 70.0
RISK_THRESHOLD = 30.0
QUALITY_WEIGHT = 0.65
RISK_WEIGHT = 0.35
AVOID_PENALTY = 0.30


def run_fundamental_check(symbol: str, timeout: int = 300) -> Dict[str, Any]:
    """Run the vendored fundamental_check.py on one symbol; never raises.

    Returns a dict with quality/risk/avoid/coverage, or quality=None on
    failure (unresolvable ticker, insufficient data, or a subprocess error).
    """
    result = {"quality": None, "risk": None, "avoid": None, "coverage": None, "error": None}
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            [sys.executable, str(FUNDAMENTAL_CHECK), symbol],
            capture_output=True, timeout=timeout, env=env,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        result["error"] = "timed out"
        return result

    if proc.returncode == 2:
        first_line = (proc.stderr or "").strip().splitlines()
        result["error"] = first_line[0] if first_line else "unresolvable / insufficient data"
        return result

    json_line = next((ln for ln in (proc.stdout or "").splitlines() if ln.startswith("JSON: ")), None)
    if not json_line:
        result["error"] = "no JSON path reported"
        return result

    jpath = Path(json_line[len("JSON: "):].strip())
    try:
        data = json.loads(jpath.read_text(encoding="utf-8"))
        result.update(
            quality=float(data["quality"]),
            risk=float(data["risk"]),
            avoid=bool(data["avoid"]),
            coverage=float(data.get("coverage", 0.0)),
        )
    except Exception as e:
        result["error"] = f"could not read report JSON ({type(e).__name__})"
    return result


class V7FundamentalCheckAlgorithm(BaseAlgorithm):
    """Wraps fundamental-check's Quality/Risk score as a BaseAlgorithm."""

    version = AlgorithmVersion.V7_FUNDAMENTAL_CHECK

    def calculate_metrics(
        self,
        symbol: str,
        history: pd.DataFrame,
        info: Dict[str, Any],
        benchmark_yield: float = 1.5,
    ) -> Dict[str, float]:
        check = run_fundamental_check(symbol)
        if check["quality"] is None:
            # Unresolvable / insufficient data / subprocess failure: degrade to
            # the worst possible signature rather than raising, consistent with
            # how the other algorithms handle missing data.
            return {
                "Quality Score": 0.0,
                "Risk Score": 100.0,
                "AVOID": 1.0,
                "Coverage (%)": 0.0,
            }
        return {
            "Quality Score": check["quality"],
            "Risk Score": check["risk"],
            "AVOID": 1.0 if check["avoid"] else 0.0,
            "Coverage (%)": round(check["coverage"] * 100.0, 1),
        }

    def calculate_scores(
        self,
        metrics: Dict[str, float],
        benchmark_yield: float = 1.5,
    ) -> Tuple[Dict[str, float], float, float, float, Dict[str, Tuple[float, str]], Dict[str, float]]:
        thresholds = {
            "Quality Score": (QUALITY_THRESHOLD, ">"),
            "Risk Score": (RISK_THRESHOLD, "<"),
        }
        weights = {
            "Quality Score": QUALITY_WEIGHT,
            "Risk Score": RISK_WEIGHT,
        }

        quality = metrics.get("Quality Score", 0.0)
        risk = metrics.get("Risk Score", 100.0)
        raw_scores = {
            "Quality Score": quality / 100.0,
            "Risk Score": 1.0 - risk / 100.0,
        }

        initial_score = sum(raw_scores[c] * weights[c] for c in weights)
        penalties = AVOID_PENALTY if metrics.get("AVOID", 0.0) >= 1.0 else 0.0
        final_score = max(0.0, initial_score - penalties)

        return raw_scores, initial_score, penalties, final_score, thresholds, weights

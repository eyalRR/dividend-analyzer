"""Check whether v7_fundamental_check's Quality/Risk scores agree with V1-V6,
and plot a scatter-subplot grid (quality vs each V1-V6, risk vs each V1-V6).

Usage:
    python scripts/compare_v7_agreement.py --scores scores.csv --out charts/v7_agreement.png
"""
import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

V1_V6 = [
    "v1_linear",
    "v2_sigmoid",
    "v3_exponential",
    "v4_penalty_weighted",
    "v5_dividend_value",
    "v6_modern_corrected",
]


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=str, default="scores.csv")
    parser.add_argument("--out", type=str, default="charts/v7_agreement.png")
    args = parser.parse_args()

    rows = load_rows(args.scores)

    data = {"quality": [], "risk": []}
    for v in V1_V6:
        data[v] = []

    for r in rows:
        q = to_float(r.get("quality"))
        risk = to_float(r.get("risk"))
        if q is None or risk is None:
            continue
        v_vals = {v: to_float(r.get(v)) for v in V1_V6}
        if any(v_vals[v] is None for v in V1_V6):
            continue
        data["quality"].append(q)
        data["risk"].append(risk)
        for v in V1_V6:
            data[v].append(v_vals[v])

    n = len(data["quality"])
    print(f"Usable rows (quality/risk + all V1-V6 present): {n}")

    fig, axes = plt.subplots(2, 6, figsize=(24, 8))
    corr_report = []

    for col, v in enumerate(V1_V6):
        x = np.array(data[v])

        # Row 0: Quality vs V1-V6
        y_q = np.array(data["quality"])
        ax = axes[0, col]
        ax.scatter(x, y_q, s=10, alpha=0.4, color="#2563eb")
        r_q = np.corrcoef(x, y_q)[0, 1]
        ax.set_title(f"{v}\nr={r_q:.2f}", fontsize=10)
        ax.set_xlabel(v, fontsize=8)
        if col == 0:
            ax.set_ylabel("V7 Quality Score", fontsize=9)
        ax.grid(True, linestyle="--", alpha=0.4)
        corr_report.append(("Quality", v, r_q))

        # Row 1: Risk vs V1-V6
        y_r = np.array(data["risk"])
        ax2 = axes[1, col]
        ax2.scatter(x, y_r, s=10, alpha=0.4, color="#dc2626")
        r_r = np.corrcoef(x, y_r)[0, 1]
        ax2.set_title(f"r={r_r:.2f}", fontsize=10)
        ax2.set_xlabel(v, fontsize=8)
        if col == 0:
            ax2.set_ylabel("V7 Risk Score", fontsize=9)
        ax2.grid(True, linestyle="--", alpha=0.4)
        corr_report.append(("Risk", v, r_r))

    fig.suptitle(f"V7 Fundamental Check (Quality/Risk) vs V1-V6 Dividend Scores (n={n})", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150)
    print(f"[OK] Saved chart to {out_path}")

    print("\nPearson correlation (r) summary:")
    print(f"{'Metric':<8} {'vs':<22} {'r':>6}")
    for metric, v, r in corr_report:
        print(f"{metric:<8} {v:<22} {r:>6.2f}")


if __name__ == "__main__":
    main()

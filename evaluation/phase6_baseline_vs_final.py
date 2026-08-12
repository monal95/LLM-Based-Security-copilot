"""Phase 6 Baseline vs Final Comparison & Visualization.

Compares Baseline config (baseline_config.json) against Final/Best config (best_config.json)
evaluated on the exact same 300-query benchmark.

Outputs:
  - evaluation/results/baseline_vs_final.json
  - evaluation/results/baseline_vs_final.csv
  - evaluation/results/baseline_vs_final.png
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server/CLI script
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.evaluation_engine import EvaluationConfig, load_config
from evaluation.phase6_retrieval_evaluation import evaluate_mode, load_phase6_queries

LOGGER = logging.getLogger(__name__)

BASELINE_CONFIG_PATH = PROJECT_ROOT / "evaluation" / "baseline_config.json"
BEST_CONFIG_PATH = PROJECT_ROOT / "evaluation" / "experiments" / "best_config.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"


def run_comparison() -> Dict[str, Any]:
    queries = load_phase6_queries()
    baseline_cfg = load_config(BASELINE_CONFIG_PATH)
    final_cfg = load_config(BEST_CONFIG_PATH)

    modes = ["dense", "sparse", "hybrid", "full"]
    comparison: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "query_count": len(queries),
        "baseline_config": baseline_cfg.to_dict(),
        "final_config": final_cfg.to_dict(),
        "metrics_by_mode": {},
    }

    metrics_keys = ["recall_5", "recall_10", "precision_5", "precision_10", "mrr", "ndcg_5", "ndcg_10", "avg_latency_ms"]

    for mode in modes:
        LOGGER.info("Evaluating Baseline for mode: %s...", mode)
        base_res, _ = evaluate_mode(queries, mode, baseline_cfg)

        LOGGER.info("Evaluating Final for mode: %s...", mode)
        final_res, _ = evaluate_mode(queries, mode, final_cfg)

        mode_diff = {}
        for k in metrics_keys:
            b_val = float(base_res.get(k, 0.0))
            f_val = float(final_res.get(k, 0.0))
            abs_diff = f_val - b_val
            pct_diff = ((f_val - b_val) / b_val * 100.0) if b_val > 0 else 0.0

            mode_diff[k] = {
                "baseline": round(b_val, 4),
                "final": round(f_val, 4),
                "absolute_improvement": round(abs_diff, 4),
                "percentage_improvement": round(pct_diff, 2),
            }

        comparison["metrics_by_mode"][mode] = mode_diff

    return comparison


def generate_artifacts(comparison: Dict[str, Any]):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save JSON
    json_path = RESULTS_DIR / "baseline_vs_final.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)
    LOGGER.info("Saved comparison JSON -> %s", json_path)

    # 2. Save CSV
    csv_path = RESULTS_DIR / "baseline_vs_final.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Mode", "Metric", "Baseline", "Final", "Abs Diff", "% Improvement"])
        for mode, metrics in comparison["metrics_by_mode"].items():
            for m_key, vals in metrics.items():
                writer.writerow([
                    mode, m_key, vals["baseline"], vals["final"],
                    vals["absolute_improvement"], f"{vals['percentage_improvement']}%"
                ])
    LOGGER.info("Saved comparison CSV -> %s", csv_path)

    # 3. Save Visualization PNG
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    modes = ["dense", "sparse", "hybrid", "full"]
    metrics_to_plot = ["recall_5", "mrr", "ndcg_5", "ndcg_10"]

    x = np.arange(len(modes))
    width = 0.35

    for ax_idx, m_key in enumerate(metrics_to_plot):
        row, col = divmod(ax_idx, 2)
        ax = axes[row, col]

        base_vals = [comparison["metrics_by_mode"][m][m_key]["baseline"] for m in modes]
        final_vals = [comparison["metrics_by_mode"][m][m_key]["final"] for m in modes]

        rects1 = ax.bar(x - width/2, base_vals, width, label="Baseline", color="#6c757d")
        rects2 = ax.bar(x + width/2, final_vals, width, label="Final (Optimized)", color="#0d6efd")

        ax.set_ylabel("Score")
        ax.set_title(f"Baseline vs Final: {m_key.upper()}")
        ax.set_xticks(x)
        ax.set_xticklabels([m.upper() for m in modes])
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.7)

        # Value labels on top of bars
        for rect in rects1 + rects2:
            height = rect.get_height()
            ax.annotate(f"{height:.3f}",
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),  # 3 points vertical offset
                        textcoords="offset points",
                        ha="center", va="bottom", fontsize=8)

    plt.tight_layout()
    png_path = RESULTS_DIR / "baseline_vs_final.png"
    plt.savefig(png_path, dpi=300)
    plt.close()
    LOGGER.info("Saved comparison plot -> %s", png_path)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    comparison = run_comparison()
    generate_artifacts(comparison)

    print("\n" + "=" * 80)
    print("BASELINE VS FINAL RETRIEVAL COMPARISON (300 QUERIES)")
    print("=" * 80)
    print(f"{'Mode':<8} | {'Metric':<12} | {'Baseline':<9} | {'Final':<9} | {'Abs Diff':<9} | {'% Change':<9}")
    print("-" * 80)
    for mode, metrics in comparison["metrics_by_mode"].items():
        for m_key in ["recall_5", "mrr", "ndcg_5", "avg_latency_ms"]:
            v = metrics[m_key]
            print(f"{mode:<8} | {m_key:<12} | {v['baseline']:<9.4f} | {v['final']:<9.4f} | {v['absolute_improvement']:<9.4f} | {v['percentage_improvement']:<+8.2f}%")
    print("=" * 80)


if __name__ == "__main__":
    main()

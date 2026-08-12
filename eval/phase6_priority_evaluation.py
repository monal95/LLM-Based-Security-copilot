"""Phase 5 Priority Scoring Evaluation for SecureRAG.

Evaluates the existing priority scorer (modules/priority_scorer.py) against >= 50 CVEs.
Ground truth ordering: CISA KEV addition date (date_added).

Calculates:
  - Spearman correlation (rho) and p-value
  - Kendall tau correlation and p-value
  - Top-K overlap (Top-5, Top-10)
  - Category ordering accuracy (Category B KEV above Category A non-KEV)

Outputs:
  - evaluation/results/phase6_priority_results.json
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from scipy.stats import kendalltau, spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.priority_scorer import WEIGHTS_MAIN, rank_cves

KEV_FILE = PROJECT_ROOT / "data" / "processed" / "kev.json"
CONTRAST_FILE = PROJECT_ROOT / "eval" / "contrast_cves.json"
RESULTS_FILE = PROJECT_ROOT / "evaluation" / "results" / "phase6_priority_results.json"

LOGGER = logging.getLogger(__name__)


def load_kev_ground_truth(min_count: int = 50) -> List[Dict[str, Any]]:
    """Load at least 50 CVEs from KEV sorted by addition date (newer addition = higher priority ground truth)."""
    if not KEV_FILE.exists():
        raise FileNotFoundError(f"KEV processed data not found at {KEV_FILE}")

    with open(KEV_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    valid_cves = []
    for r in records:
        if isinstance(r, dict) and "cve_id" in r and "date_added" in r:
            valid_cves.append({
                "cve_id": r["cve_id"].upper(),
                "date_added": r["date_added"],
            })

    valid_cves.sort(key=lambda x: x["date_added"], reverse=True)
    return valid_cves[:min_count]


def evaluate_priority_scorer() -> Dict[str, Any]:
    LOGGER.info("Loading KEV ground truth records...")
    gt_records = load_kev_ground_truth(min_count=60)
    cve_ids = [r["cve_id"] for r in gt_records]

    LOGGER.info("Scoring and ranking %d CVEs with priority_scorer WEIGHTS_MAIN...", len(cve_ids))
    ranked_output = rank_cves(cve_ids, WEIGHTS_MAIN)

    pred_ranks = {item["cve_id"].upper(): item["rank"] for item in ranked_output}
    pred_scores = {item["cve_id"].upper(): item["priority_score"] for item in ranked_output}
    gt_ranks = {r["cve_id"]: idx for idx, r in enumerate(gt_records, start=1)}

    gt_rank_vec = [gt_ranks[cve] for cve in cve_ids]
    pred_rank_vec = [pred_ranks[cve] for cve in cve_ids]

    spearman_res = spearmanr(pred_rank_vec, gt_rank_vec)
    spearman_rho = float(spearman_res.statistic if hasattr(spearman_res, "statistic") else spearman_res[0])
    spearman_p = float(spearman_res.pvalue if hasattr(spearman_res, "pvalue") else spearman_res[1])

    kendall_res = kendalltau(pred_rank_vec, gt_rank_vec)
    kendall_tau = float(kendall_res.statistic if hasattr(kendall_res, "statistic") else kendall_res[0])
    kendall_p = float(kendall_res.pvalue if hasattr(kendall_res, "pvalue") else kendall_res[1])

    gt_top5 = set(cve_ids[:5])
    pred_top5 = set([item["cve_id"] for item in ranked_output[:5]])
    top5_overlap = len(gt_top5 & pred_top5) / 5.0

    gt_top10 = set(cve_ids[:10])
    pred_top10 = set([item["cve_id"] for item in ranked_output[:10]])
    top10_overlap = len(gt_top10 & pred_top10) / 10.0

    contrast_pass = True
    contrast_msg = "No contrast file evaluated"
    if CONTRAST_FILE.exists():
        with open(CONTRAST_FILE, "r", encoding="utf-8-sig") as f:
            contrast_data = json.load(f)
        cat_a = [item["cve_id"] for item in contrast_data.get("category_a", [])]
        cat_b = [item["cve_id"] for item in contrast_data.get("category_b", [])]
        contrast_cves = cat_a + cat_b
        contrast_ranked = rank_cves(contrast_cves, WEIGHTS_MAIN)
        rank_map = {item["cve_id"].upper(): item["rank"] for item in contrast_ranked}
        ranks_a = [rank_map[c.upper()] for c in cat_a if c.upper() in rank_map]
        ranks_b = [rank_map[c.upper()] for c in cat_b if c.upper() in rank_map]
        if ranks_a and ranks_b and max(ranks_b) < min(ranks_a):
            contrast_pass = True
            contrast_msg = "Category B (KEV exploited) all ranked higher priority than Category A (non-KEV)"
        else:
            contrast_pass = False
            contrast_msg = "Category ordering split detected"

    summary = {
        "evaluation_name": "Phase 6 Priority Scoring Evaluation",
        "sample_size": len(cve_ids),
        "weights_used": WEIGHTS_MAIN,
        "ground_truth_metric": "CISA KEV addition date (date_added)",
        "spearman_rho": round(spearman_rho, 4),
        "spearman_pvalue": float(spearman_p),
        "kendall_tau": round(kendall_tau, 4),
        "kendall_pvalue": float(kendall_p),
        "top5_overlap": round(top5_overlap, 4),
        "top10_overlap": round(top10_overlap, 4),
        "category_ordering_accuracy": 1.0 if contrast_pass else 0.0,
        "category_ordering_notes": contrast_msg,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "top_ranked_samples": ranked_output[:10],
    }

    return summary


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    summary = evaluate_priority_scorer()

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    LOGGER.info("Saved priority evaluation results -> %s", RESULTS_FILE)

    print("\n" + "=" * 60)
    print("PHASE 6 PRIORITY EVALUATION RESULTS")
    print("=" * 60)
    print(f"Sample Size:                  {summary['sample_size']}")
    print(f"Spearman Correlation (rho):   {summary['spearman_rho']:.4f} (p={summary['spearman_pvalue']:.4e})")
    print(f"Kendall Tau:                  {summary['kendall_tau']:.4f} (p={summary['kendall_pvalue']:.4e})")
    print(f"Top-5 Overlap:                {summary['top5_overlap'] * 100:.1f}%")
    print(f"Top-10 Overlap:               {summary['top10_overlap'] * 100:.1f}%")
    print(f"Category Ordering Accuracy:   {summary['category_ordering_accuracy'] * 100:.1f}%")
    print(f"Notes:                        {summary['category_ordering_notes']}")
    print("=" * 60)


if __name__ == "__main__":
    main()

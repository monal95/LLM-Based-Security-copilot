"""Validation script for the SecureRAG Phase 5 prioritization engine.

This script loads contrast CVEs discovered from the real NVD/KEV/EPSS data,
scores them under three weight presets, reports ranking and correlation
statistics, and saves the combined results to ``eval/validation_results_v2.json``.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.priority_scorer import (
    WEIGHTS_MAIN,
    WEIGHTS_ABLATION1,
    WEIGHTS_ABLATION2,
    rank_cves,
)

LOGGER = logging.getLogger(__name__)
CONTRAST_FILE = PROJECT_ROOT / "eval" / "contrast_cves.json"
OUTPUT_FILE = PROJECT_ROOT / "eval" / "validation_results_v2.json"


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _load_contrast() -> Dict[str, List[Dict[str, Any]]]:
    if not CONTRAST_FILE.exists():
        raise FileNotFoundError(f"Contrast file not found: {CONTRAST_FILE}")
    try:
        # Use utf-8-sig to tolerate BOM if PowerShell wrote a BOM
        with CONTRAST_FILE.open("r", encoding="utf-8-sig") as fh:
            payload = json.load(fh)
    except Exception as exc:
        raise RuntimeError(f"Failed to load contrast file: {CONTRAST_FILE}") from exc
    return payload


def _flatten_contrast(payload: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, items in payload.items():
        cat = key.lower()
        for item in items:
            item_copy = dict(item)
            item_copy["category"] = cat
            out.append(item_copy)
    return out


def _format_score(value: Any) -> str:
    try:
        return f"{float(value):.4f}"
    except Exception:
        return "0.0000"


def _compute_spearman(priority_scores: Sequence[float], epss_probs: Sequence[float]) -> Dict[str, Any]:
    try:
        from scipy.stats import spearmanr  # type: ignore
    except Exception:
        LOGGER.warning("scipy not available; skipping Spearman correlation")
        return {"rho": None, "pvalue": None}

    try:
        rho, pval = spearmanr(priority_scores, epss_probs)
        return {"rho": float(rho), "pvalue": float(pval)}
    except Exception as exc:
        LOGGER.exception("Spearman computation failed")
        return {"rho": None, "pvalue": None}


def _assert_category_b_above_a(ranked: List[Dict[str, Any]], category_a: List[str], category_b: List[str]) -> tuple[bool, str]:
    # build rank map
    rank_map = {str(item.get("cve_id", "")).upper(): int(item.get("rank", 10**9)) for item in ranked}
    ranks_a = [rank_map.get(cve.upper(), 10**9) for cve in category_a]
    ranks_b = [rank_map.get(cve.upper(), 0) for cve in category_b]
    if not ranks_a or not ranks_b:
        return False, "One of the categories is empty in the ranked results"
    # All B ranks must be numerically less (higher priority) than all A ranks
    if max(ranks_b) < min(ranks_a):
        return True, "All Category B CVEs ranked above all Category A CVEs"
    return False, "Not all Category B CVEs ranked above Category A CVEs"


def _print_table(ranked: List[Dict[str, Any]]) -> None:
    print()
    print("Rank | CVE ID         | CVSS  | EPSS%   | KEV | Score   | Category")
    print("-" * 84)
    for item in ranked:
        print(
            f"{int(item.get('rank',0)):>4} | "
            f"{str(item.get('cve_id','')):<14} | "
            f"{_format_score(item.get('cvss_score')):>5} | "
            f"{_format_score(float(item.get('epss_score',0.0))*100.0):>7}% | "
            f"{int(item.get('kev_flag',0)):>3} | "
            f"{_format_score(item.get('priority_score')):>7} | "
            f"{str(item.get('category','')):>8}"
        )


def main() -> int:
    _configure_logging()
    print("Loading contrast CVEs from:", CONTRAST_FILE)
    contrast = _load_contrast()
    flat = _flatten_contrast(contrast)
    cve_list = [str(item.get("cve_id","")) for item in flat]

    if len(cve_list) == 0:
        print("No contrast CVEs found; run find_contrast_cves.ps1 first.")
        return 2

    presets = {
        "WEIGHTS_MAIN": WEIGHTS_MAIN,
        "WEIGHTS_ABLATION1": WEIGHTS_ABLATION1,
        "WEIGHTS_ABLATION2": WEIGHTS_ABLATION2,
    }

    summary: Dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat(), "presets": {}}

    for name, weights in presets.items():
        print(f"\nRunning preset: {name}")
        ranked = rank_cves(cve_list, weights)
        # attach category labels from flat
        id_to_cat = {str(item.get("cve_id","")).upper(): item.get("category","unknown") for item in flat}
        for item in ranked:
            item_id = str(item.get("cve_id","")).upper()
            item["category"] = id_to_cat.get(item_id, "unknown")

        # compute spearman between priority score and epss
        priority_scores = [float(item.get("priority_score", 0.0)) for item in ranked]
        epss_probs = [float(item.get("epss_score", 0.0)) for item in ranked]
        spearman = _compute_spearman(priority_scores, epss_probs)
        print(f"Spearman correlation (priority vs EPSS): rho={spearman.get('rho')} p={spearman.get('pvalue')}")

        # core assertion: all category B above all category A
        category_a = [it.get("cve_id") for it in contrast.get("category_a", [])]
        category_b = [it.get("cve_id") for it in contrast.get("category_b", [])]
        passed, message = _assert_category_b_above_a(ranked, category_a, category_b)
        print(f"Core assertion: {'PASS' if passed else 'FAIL'} - {message}")

        _print_table(ranked)

        summary["presets"][name] = {
            "weights": dict(weights),
            "ranked_cves": ranked,
            "spearman": spearman,
            "core_assertion_passed": bool(passed),
            "core_assertion_message": message,
        }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    any_failures = any(not p["core_assertion_passed"] for p in summary["presets"].values())
    print("PASS" if not any_failures else "FAIL")
    return 0 if not any_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
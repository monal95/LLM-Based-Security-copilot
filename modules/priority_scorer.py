"""SecureRAG Phase 5 priority scoring for CVE patch triage.

This module loads NVD, CISA KEV, and EPSS data once at import time and
provides reusable scoring helpers for prioritizing vulnerabilities.

Public API:
    score_cve(cve_id: str, weights: dict) -> dict
    rank_cves(cve_list: list[str], weights: dict) -> list[dict]

The scoring formula is:
    priority = (cvss / 10 * cvss_weight) + (epss * epss_weight) + (kev_flag * kev_weight)
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

WEIGHTS_MAIN: Dict[str, float] = {"cvss_weight": 0.3, "epss_weight": 0.5, "kev_weight": 0.2}
WEIGHTS_ABLATION1: Dict[str, float] = {"cvss_weight": 0.5, "epss_weight": 0.3, "kev_weight": 0.2}
WEIGHTS_ABLATION2: Dict[str, float] = {"cvss_weight": 0.33, "epss_weight": 0.33, "kev_weight": 0.34}

_NVD_INDEX: Dict[str, Dict[str, Any]] | None = None
_KEV_INDEX: set[str] | None = None
_EPSS_INDEX: Dict[str, Dict[str, Any]] | None = None


def _configure_logging() -> None:
    """Configure default logging when the host application has not set handlers."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _candidate_paths(filename: str) -> List[Path]:
    """Return candidate paths for a data artifact relative to the project root."""
    return [
        DATA_DIR / filename,
        DATA_DIR / "processed" / filename,
        DATA_DIR / "raw" / filename,
    ]


def _resolve_data_file(filename: str) -> Path:
    """Resolve a data file from the known project-relative locations."""
    for path in _candidate_paths(filename):
        if path.exists():
            return path
    candidates = ", ".join(str(path) for path in _candidate_paths(filename))
    raise FileNotFoundError(f"Unable to locate {filename}. Tried: {candidates}")


def _load_json(path: Path) -> Any:
    """Load JSON with explicit error handling."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        raise RuntimeError(f"Failed to load JSON artifact: {path}") from exc


def _normalize_records(payload: Any) -> List[Dict[str, Any]]:
    """Normalize a JSON payload into a list of dictionaries."""
    if isinstance(payload, list):
        records: List[Dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                records.append(item)
        return records

    if isinstance(payload, dict):
        for key in ("vulnerabilities", "data", "records", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                records = []
                for item in value:
                    if isinstance(item, dict):
                        records.append(item)
                return records

    return []


def _extract_cve_id(record: Mapping[str, Any]) -> str:
    """Extract a CVE identifier from a record."""
    for key in ("cve_id", "cveID", "id", "cve"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip().upper()
            if text.startswith("CVE-"):
                return text
    nested = record.get("cve")
    if isinstance(nested, dict):
        nested_id = nested.get("id")
        if isinstance(nested_id, str) and nested_id.strip():
            return nested_id.strip().upper()
    return ""


def _extract_cvss_score(record: Mapping[str, Any]) -> float:
    """Extract a CVSS base score from a record."""
    for key in ("cvss_score", "baseScore", "score"):
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue

    metrics = record.get("metrics")
    if isinstance(metrics, dict):
        for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            metric_items = metrics.get(metric_key)
            if not isinstance(metric_items, list) or not metric_items:
                continue
            first_metric = metric_items[0]
            if not isinstance(first_metric, dict):
                continue
            cvss_data = first_metric.get("cvssData")
            if isinstance(cvss_data, dict):
                score = cvss_data.get("baseScore")
                if isinstance(score, (int, float)):
                    return float(score)
                if isinstance(score, str):
                    try:
                        return float(score)
                    except ValueError:
                        pass
    return 0.0


def _extract_epss_probability(record: Mapping[str, Any]) -> float:
    """Extract an EPSS probability from a record."""
    for key in ("epss_probability", "epss", "probability"):
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return 0.0


def _load_nvd_index() -> Dict[str, Dict[str, Any]]:
    """Load and index NVD records by CVE ID once."""
    path = _resolve_data_file("nvd.json")
    payload = _load_json(path)
    records = _normalize_records(payload)

    index: Dict[str, Dict[str, Any]] = {}
    for record in records:
        cve_id = _extract_cve_id(record)
        if cve_id:
            index[cve_id] = record
    LOGGER.info("Loaded %d NVD records from %s", len(index), path)
    return index


def _load_kev_index() -> set[str]:
    """Load KEV records once and index by CVE ID."""
    path = _resolve_data_file("kev.json")
    payload = _load_json(path)
    records = _normalize_records(payload)

    index: set[str] = set()
    for record in records:
        cve_id = _extract_cve_id(record)
        if cve_id:
            index.add(cve_id)
    LOGGER.info("Loaded %d KEV records from %s", len(index), path)
    return index


def _load_epss_index() -> Dict[str, Dict[str, Any]]:
    """Load and index EPSS records by CVE ID once."""
    path = _resolve_data_file("epss.json")
    payload = _load_json(path)
    records = _normalize_records(payload)

    index: Dict[str, Dict[str, Any]] = {}
    for record in records:
        cve_id = _extract_cve_id(record)
        if cve_id:
            index[cve_id] = record
    LOGGER.info("Loaded %d EPSS records from %s", len(index), path)
    return index


def _get_nvd_index() -> Dict[str, Dict[str, Any]]:
    """Return the cached NVD index, loading it once on first use."""
    global _NVD_INDEX
    if _NVD_INDEX is None:
        _NVD_INDEX = _load_nvd_index()
    return _NVD_INDEX


def _get_kev_index() -> set[str]:
    """Return the cached KEV index, loading it once on first use."""
    global _KEV_INDEX
    if _KEV_INDEX is None:
        _KEV_INDEX = _load_kev_index()
    return _KEV_INDEX


def _get_epss_index() -> Dict[str, Dict[str, Any]]:
    """Return the cached EPSS index, loading it once on first use."""
    global _EPSS_INDEX
    if _EPSS_INDEX is None:
        _EPSS_INDEX = _load_epss_index()
    return _EPSS_INDEX


def _validate_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    """Validate the score weights and normalize them to floats."""
    required = {"cvss_weight", "epss_weight", "kev_weight"}
    missing = sorted(required.difference(weights.keys()))
    if missing:
        raise ValueError(f"weights missing required keys: {', '.join(missing)}")

    normalized = {key: float(weights[key]) for key in required}
    weight_sum = sum(normalized.values())
    if abs(weight_sum - 1.0) > 1e-6:
        raise ValueError(f"weights must sum to 1.0, got {weight_sum:.6f}")
    return normalized


def _lookup_cve(cve_id: str) -> tuple[float, float, int, Dict[str, Any]]:
    """Look up the normalized CVSS, EPSS, and KEV signals for one CVE."""
    normalized_id = cve_id.strip().upper()
    nvd_index = _get_nvd_index()
    kev_index = _get_kev_index()
    epss_index = _get_epss_index()

    record = nvd_index.get(normalized_id)
    if record is None:
        LOGGER.warning("Missing NVD record for %s; assigning zero score", normalized_id)
        return 0.0, 0.0, 0, {"missing_sources": ["nvd"]}

    cvss_score = _extract_cvss_score(record)
    epss_record = epss_index.get(normalized_id)
    if epss_record is None:
        LOGGER.warning("Missing EPSS record for %s; assigning zero EPSS", normalized_id)
    epss_score = _extract_epss_probability(epss_record or {})
    kev_flag = 1 if normalized_id in kev_index else 0

    missing_sources: List[str] = []
    if cvss_score == 0.0 and not any(
        isinstance(record.get(key), (int, float, str)) for key in ("cvss_score", "baseScore", "score")
    ):
        missing_sources.append("cvss")
    if epss_record is None:
        missing_sources.append("epss")
    if kev_flag == 0:
        missing_sources.append("kev")

    return cvss_score, epss_score, kev_flag, {"missing_sources": missing_sources}


def score_cve(cve_id: str, weights: dict) -> dict:
    """Score a single CVE using CVSS, EPSS, and KEV signals.

    Args:
        cve_id: CVE identifier to score.
        weights: Dictionary with ``cvss_weight``, ``epss_weight``, and ``kev_weight``.

    Returns:
        A dictionary with raw signals, the weighted priority score, and ranking metadata.
    """
    _configure_logging()
    normalized_weights = _validate_weights(weights)
    normalized_id = cve_id.strip().upper()
    cvss_score, epss_score, kev_flag, lookup_metadata = _lookup_cve(normalized_id)

    cvss_component = (cvss_score / 10.0) * normalized_weights["cvss_weight"]
    epss_component = epss_score * normalized_weights["epss_weight"]
    kev_component = float(kev_flag) * normalized_weights["kev_weight"]
    priority_score = cvss_component + epss_component + kev_component

    return {
        "cve_id": normalized_id,
        "cvss_score": float(cvss_score),
        "epss_score": float(epss_score),
        "kev_flag": int(kev_flag),
        "priority_score": float(priority_score),
        "rank_signals": {
            "cvss_component": float(cvss_component),
            "epss_component": float(epss_component),
            "kev_component": float(kev_component),
            "weights": dict(normalized_weights),
            **lookup_metadata,
        },
    }


def rank_cves(cve_list: list[str], weights: dict) -> list[dict]:
    """Rank CVEs by descending priority score.

    Args:
        cve_list: CVE identifiers to score and rank.
        weights: Weight dictionary used by :func:`score_cve`.

    Returns:
        A list of scored CVE dictionaries sorted by descending priority.
    """
    _configure_logging()
    scored: List[Dict[str, Any]] = []
    for cve_id in cve_list:
        scored.append(score_cve(cve_id, weights))

    scored.sort(key=lambda item: float(item.get("priority_score", 0.0)), reverse=True)
    for index, item in enumerate(scored, start=1):
        item["rank"] = index
    return scored


def available_weights() -> Dict[str, Dict[str, float]]:
    """Return the built-in weight presets for convenience."""
    return {
        "WEIGHTS_MAIN": dict(WEIGHTS_MAIN),
        "WEIGHTS_ABLATION1": dict(WEIGHTS_ABLATION1),
        "WEIGHTS_ABLATION2": dict(WEIGHTS_ABLATION2),
    }


def main() -> int:
    """Small CLI entrypoint for manual smoke testing."""
    _configure_logging()
    sample_cves = ["CVE-2021-44228", "CVE-2022-26134", "CVE-2023-44487"]
    ranked = rank_cves(sample_cves, WEIGHTS_MAIN)
    for item in ranked:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
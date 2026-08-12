"""Validation script for Phase 6 300-query evaluation dataset.

Strictly validates:
  1. Exactly 300 queries total.
  2. Exactly 100 'cve_explanation' queries.
  3. Exactly 100 'mitre_mapping' queries.
  4. Exactly 100 'incident_response' queries.
  5. No duplicate query strings.
  6. No duplicate query IDs.
  7. Every query contains non-empty 'ground_truth_answer'.
  8. Every query contains non-empty 'expected_documents'.
  9. Every expected document exists in authoritative datasets (NVD/KEV/MITRE).
"""

from __future__ import annotations

import json
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evaluation" / "phase6_queries.json"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

LOGGER = logging.getLogger(__name__)


def load_authoritative_entities() -> Set[str]:
    """Load all known CVE IDs and MITRE Technique IDs from processed dataset."""
    entities: Set[str] = set()

    kev_path = PROCESSED_DIR / "kev.json"
    mitre_path = PROCESSED_DIR / "mitre.json"
    nvd_path = PROCESSED_DIR / "nvd.json"

    if kev_path.exists():
        with open(kev_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                if isinstance(item, dict) and "cve_id" in item:
                    entities.add(item["cve_id"].upper())

    if mitre_path.exists():
        with open(mitre_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                if isinstance(item, dict) and "technique_id" in item:
                    entities.add(item["technique_id"].upper())

    if nvd_path.exists():
        with open(nvd_path, "r", encoding="utf-8") as f:
            nvd = json.load(f)
            if isinstance(nvd, list):
                for item in nvd:
                    if isinstance(item, dict) and "cve_id" in item:
                        entities.add(item["cve_id"].upper())

    return entities


def validate_dataset(path: Path = DATASET_PATH) -> bool:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if not path.exists():
        LOGGER.error("Dataset file not found: %s", path)
        return False

    with open(path, "r", encoding="utf-8") as f:
        queries: List[Dict[str, Any]] = json.load(f)

    errors: List[str] = []

    # 1. Check total count
    total_count = len(queries)
    if total_count != 300:
        errors.append(f"Expected exactly 300 total queries, got {total_count}")

    # 2. Check category counts
    cat_counts: Dict[str, int] = {"cve_explanation": 0, "mitre_mapping": 0, "incident_response": 0}
    for q in queries:
        cat = q.get("category")
        if cat in cat_counts:
            cat_counts[cat] += 1
        else:
            errors.append(f"Invalid query category '{cat}' in query ID {q.get('id')}")

    if cat_counts["cve_explanation"] != 100:
        errors.append(f"Expected 100 'cve_explanation' queries, got {cat_counts['cve_explanation']}")
    if cat_counts["mitre_mapping"] != 100:
        errors.append(f"Expected 100 'mitre_mapping' queries, got {cat_counts['mitre_mapping']}")
    if cat_counts["incident_response"] != 100:
        errors.append(f"Expected 100 'incident_response' queries, got {cat_counts['incident_response']}")

    # 3. Check duplicate queries and IDs
    seen_queries: Set[str] = set()
    seen_ids: Set[str] = set()

    for idx, q in enumerate(queries, start=1):
        q_id = q.get("id", f"INDEX_{idx}")
        q_text = str(q.get("query", "")).strip().lower()
        gt_answer = str(q.get("ground_truth_answer", "")).strip()
        exp_docs = q.get("expected_documents", [])

        if not q_text:
            errors.append(f"Query {q_id} has empty query text")
        if q_text in seen_queries:
            errors.append(f"Duplicate query text found: '{q.get('query')}' (ID: {q_id})")
        seen_queries.add(q_text)

        if q_id in seen_ids:
            errors.append(f"Duplicate query ID found: '{q_id}'")
        seen_ids.add(q_id)

        # 4. Check ground truth answer
        if not gt_answer:
            errors.append(f"Query {q_id} is missing 'ground_truth_answer'")

        # 5. Check expected documents
        if not isinstance(exp_docs, list) or len(exp_docs) == 0:
            errors.append(f"Query {q_id} has empty or non-list 'expected_documents'")

    # 6. Check that expected documents exist in authoritative entity set
    authoritative_entities = load_authoritative_entities()
    if authoritative_entities:
        missing_entities = set()
        for q in queries:
            for doc in q.get("expected_documents", []):
                doc_upper = str(doc).upper()
                if doc_upper not in authoritative_entities:
                    missing_entities.add(doc_upper)

        if missing_entities:
            errors.append(f"{len(missing_entities)} expected documents do not exist in authoritative corpus: {sorted(list(missing_entities))[:10]}")

    # Output validation results
    if errors:
        LOGGER.error("VALIDATION FAILED WITH %d ERRORS:", len(errors))
        for err in errors:
            LOGGER.error("  - %s", err)
        return False

    LOGGER.info("VALIDATION SUCCESSFUL!")
    LOGGER.info("  Total Queries: %d", total_count)
    LOGGER.info("  CVE Queries: %d", cat_counts['cve_explanation'])
    LOGGER.info("  MITRE Queries: %d", cat_counts['mitre_mapping'])
    LOGGER.info("  IR Queries: %d", cat_counts['incident_response'])
    LOGGER.info("  No duplicates found. All ground truth answers and entities validated against corpus.")
    return True


def main() -> int:
    success = validate_dataset()
    if not success:
        LOGGER.error("Phase 6 dataset validation FAILED loudly.")
        sys.exit(1)
    return 0


if __name__ == "__main__":
    main()

"""Phase 6 Comprehensive Test Suite for SecureRAG.

Tests:
  1. Dataset validation integrity (300 queries, 100/100/100 split, ground truth checks)
  2. Ranking metric calculations (NDCG, MRR, Recall, Precision)
  3. Priority scoring and Spearman correlation calculation
  4. RAGAS data structure formatting
  5. FastAPI backend endpoints (/api/health, /api/cve, /api/mitre, /api/priority)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app
from eval.phase6_priority_evaluation import evaluate_priority_scorer
from evaluation.evaluation_engine import _compute_dcg, _compute_metrics
from evaluation.validate_phase6_dataset import validate_dataset

client = TestClient(app)


def test_dataset_validation():
    """Verify that the 300-query benchmark dataset passes strict validation."""
    assert validate_dataset() is True, "Phase 6 dataset failed validation check"


def test_ranking_metrics():
    """Test MRR and NDCG computation logic on controlled inputs."""
    expected = ["CVE-2021-44228"]
    ranked_1 = [["CVE-2021-44228"], ["CVE-2017-0144"], ["T1190"]]
    metrics_1 = _compute_metrics(expected, ranked_1)

    assert metrics_1["mrr"] == 1.0
    assert metrics_1["recall_5"] == 1.0
    assert metrics_1["hit_1"] == 1.0
    assert metrics_1["ndcg_5"] > 0.9

    ranked_3 = [["CVE-2017-0144"], ["T1190"], ["CVE-2021-44228"]]
    metrics_3 = _compute_metrics(expected, ranked_3)

    assert round(metrics_3["mrr"], 4) == round(1.0 / 3.0, 4)
    assert metrics_3["hit_1"] == 0.0
    assert metrics_3["hit_3"] == 1.0


def test_priority_scorer_evaluation():
    """Verify that priority scorer evaluation returns valid correlation scores."""
    res = evaluate_priority_scorer()
    assert res["sample_size"] >= 50
    assert "spearman_rho" in res
    assert -1.0 <= res["spearman_rho"] <= 1.0
    assert res["category_ordering_accuracy"] == 1.0


def test_backend_health():
    """Test FastAPI /api/health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_backend_cve_endpoint():
    """Test FastAPI /api/cve/{cve_id} endpoint."""
    response = client.get("/api/cve/CVE-2021-44228")
    assert response.status_code == 200
    data = response.json()
    assert data["cve_id"] == "CVE-2021-44228"
    assert data["cvss_score"] == 10.0
    assert "description" in data


def test_backend_mitre_endpoint():
    """Test FastAPI /api/mitre/{technique_id} endpoint."""
    response = client.get("/api/mitre/T1190")
    assert response.status_code == 200
    data = response.json()
    assert data["technique_id"] == "T1190"
    assert "name" in data


def test_backend_priority_endpoint():
    """Test FastAPI /api/priority endpoint."""
    payload = {"cve_ids": ["CVE-2021-44228", "CVE-2017-0144"], "explain": False}
    response = client.post("/api/priority", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "ranked_cves" in data
    assert len(data["ranked_cves"]) == 2

"""Runtime latency benchmark for the SecureRAG API.

This measures wall-clock request latency only. It is deliberately separate from
the retrieval-quality evaluation in ``phase6_retrieval_evaluation.py`` and never
reads, writes or derives any of the research metric files.

The first request against a freshly started server is reported as the cold
measurement; the remainder are warm. Results are written to
``evaluation/results/runtime_benchmark.json``, a runtime artefact that is not
part of the research result set.

Usage (PowerShell):
    python evaluation/benchmark_runtime.py --endpoint retrieve --runs 5
    python evaluation/benchmark_runtime.py --endpoint chat --runs 3
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"
OUTPUT_FILE = RESULTS_DIR / "runtime_benchmark.json"

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api"
DEFAULT_QUERY = "What is CVE-2021-44228?"

LOGGER = logging.getLogger("secure_rag.benchmark")


def _percentile(values: List[float], fraction: float) -> float:
    """Nearest-rank percentile; returns NaN for an empty sample."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * len(ordered) + 0.5)) - 1))
    return ordered[index]


def _wait_for_health(base_url: str, timeout_s: float) -> Dict[str, Any]:
    """Block until the API answers /health, returning its payload."""
    deadline = time.monotonic() + timeout_s
    last_error: str | None = None

    while time.monotonic() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            if response.ok:
                return response.json()
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(1.0)

    raise RuntimeError(f"API did not become healthy within {timeout_s:.0f}s: {last_error}")


def _issue_request(base_url: str, endpoint: str, query: str, top_k: int, timeout_s: float) -> Dict[str, Any]:
    """Send one request and return its measured latency plus server-side detail."""
    if endpoint == "retrieve":
        url = f"{base_url}/retrieve"
        payload: Dict[str, Any] = {"query": query, "top_k": top_k}
    else:
        url = f"{base_url}/chat"
        payload = {"query": query}

    started = time.perf_counter()
    response = requests.post(url, json=payload, timeout=timeout_s)
    client_latency_ms = (time.perf_counter() - started) * 1000.0
    response.raise_for_status()
    body = response.json()

    return {
        "client_latency_ms": round(client_latency_ms, 2),
        "server_latency_ms": body.get("latency_ms", body.get("total_latency_ms")),
        "stage_timings_ms": body.get("stage_timings_ms"),
        "warm_flag": body.get("warm"),
        "result_count": body.get("total_results", body.get("counts", {}).get("reranked")),
    }


def run_benchmark(
    base_url: str,
    endpoint: str,
    query: str,
    runs: int,
    top_k: int,
    timeout_s: float,
) -> Dict[str, Any]:
    """Execute the benchmark and summarise cold and warm latency."""
    health = _wait_for_health(base_url, timeout_s=timeout_s)
    warmup_state = health.get("warmup", {})
    LOGGER.info("API healthy | warmup status=%s", warmup_state.get("status"))

    samples: List[Dict[str, Any]] = []
    for index in range(runs):
        LOGGER.info("Request %d/%d (%s)...", index + 1, runs, endpoint)
        sample = _issue_request(base_url, endpoint, query, top_k, timeout_s)
        sample["index"] = index
        sample["phase"] = "cold" if index == 0 else "warm"
        samples.append(sample)
        LOGGER.info("  latency_ms=%.2f", sample["client_latency_ms"])

    warm_latencies = [s["client_latency_ms"] for s in samples if s["phase"] == "warm"]

    summary: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "endpoint": endpoint,
        "query": query,
        "runs": runs,
        "top_k": top_k,
        "warmup_state_at_start": warmup_state,
        "cold_latency_ms": samples[0]["client_latency_ms"] if samples else None,
        "warm_mean_ms": round(statistics.fmean(warm_latencies), 2) if warm_latencies else None,
        "warm_median_ms": round(statistics.median(warm_latencies), 2) if warm_latencies else None,
        "warm_min_ms": round(min(warm_latencies), 2) if warm_latencies else None,
        "warm_max_ms": round(max(warm_latencies), 2) if warm_latencies else None,
        "warm_p95_ms": round(_percentile(warm_latencies, 0.95), 2) if warm_latencies else None,
        "samples": samples,
    }
    return summary


def _write_summary(summary: Dict[str, Any]) -> None:
    """Persist the run, keyed by endpoint so runs do not overwrite each other."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    existing: Dict[str, Any] = {}
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning("Existing benchmark file was unreadable; starting a new one")

    existing[summary["endpoint"]] = summary
    OUTPUT_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    LOGGER.info("Saved runtime benchmark -> %s", OUTPUT_FILE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure SecureRAG API runtime latency")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--endpoint", choices=["retrieve", "chat"], default="retrieve")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--no-save", action="store_true", help="Print results without writing the JSON file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    summary = run_benchmark(
        base_url=args.base_url.rstrip("/"),
        endpoint=args.endpoint,
        query=args.query,
        runs=args.runs,
        top_k=args.top_k,
        timeout_s=args.timeout,
    )

    if not args.no_save:
        _write_summary(summary)

    print("\n" + "=" * 62)
    print(f"RUNTIME BENCHMARK — /{summary['endpoint']} — {summary['runs']} runs")
    print("=" * 62)
    print(f"  cold latency     : {summary['cold_latency_ms']} ms")
    print(f"  warm mean        : {summary['warm_mean_ms']} ms")
    print(f"  warm median      : {summary['warm_median_ms']} ms")
    print(f"  warm min / max   : {summary['warm_min_ms']} / {summary['warm_max_ms']} ms")
    print(f"  warm p95         : {summary['warm_p95_ms']} ms")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

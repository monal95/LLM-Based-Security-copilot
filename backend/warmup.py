"""Startup warmup for the SecureRAG API.

The retrieval modules cache their models and indexes per process, but the cache
is populated lazily — so without this module the first analyst query pays the
full cost of importing torch, loading two transformer models, opening ChromaDB
and unpickling the BM25 artefacts.

Warmup runs those loads once on a background thread at application startup. The
server binds and answers ``/api/health`` immediately; the recorded timings are
real measurements taken during that run, never estimates.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from modules.Retrieval import dense_retriever, reranker, sparse_retriever

LOGGER = logging.getLogger("secure_rag.warmup")

_LOCK = threading.Lock()
_THREAD: Optional[threading.Thread] = None

_STATE: Dict[str, Any] = {
    "status": "not_started",  # not_started | running | ready | failed
    "started_at_monotonic": None,
    "elapsed_ms": None,
    "stages": {},
    "error": None,
}


def get_state() -> Dict[str, Any]:
    """Return a snapshot of warmup progress for health reporting."""
    with _LOCK:
        snapshot = {
            "status": _STATE["status"],
            "elapsed_ms": _STATE["elapsed_ms"],
            "stages": dict(_STATE["stages"]),
            "error": _STATE["error"],
        }

    if snapshot["status"] == "running" and _STATE["started_at_monotonic"] is not None:
        snapshot["elapsed_ms"] = round((time.monotonic() - _STATE["started_at_monotonic"]) * 1000.0, 2)

    return snapshot


def is_ready() -> bool:
    """True once every component has been loaded into the process cache."""
    with _LOCK:
        return _STATE["status"] == "ready"


def run_warmup() -> Dict[str, Any]:
    """Load every retrieval component synchronously and record real timings.

    Safe to call more than once: the underlying loaders are cached, so repeat
    calls are effectively free and simply re-record near-zero timings.

    Returns:
        The warmup state snapshot, including per-stage elapsed milliseconds.
    """
    with _LOCK:
        _STATE["status"] = "running"
        _STATE["started_at_monotonic"] = time.monotonic()
        _STATE["stages"] = {}
        _STATE["error"] = None

    overall_started = time.perf_counter()
    stages: Dict[str, float] = {}

    try:
        for label, loader in (
            ("dense", dense_retriever.warmup),
            ("sparse", sparse_retriever.warmup),
            ("reranker", reranker.warmup),
        ):
            LOGGER.info("Warmup stage starting: %s", label)
            stage_timings = loader()
            stages.update(stage_timings)
            LOGGER.info(
                "Warmup stage complete: %s | %s",
                label,
                " ".join(f"{key}={value:.0f}" for key, value in stage_timings.items()),
            )

        elapsed_ms = round((time.perf_counter() - overall_started) * 1000.0, 2)
        with _LOCK:
            _STATE["status"] = "ready"
            _STATE["stages"] = stages
            _STATE["elapsed_ms"] = elapsed_ms

        LOGGER.info("Warmup complete | total_ms=%.0f | %s", elapsed_ms, stages)

    except Exception as exc:  # noqa: BLE001 - surfaced through /api/health
        elapsed_ms = round((time.perf_counter() - overall_started) * 1000.0, 2)
        LOGGER.exception("Warmup failed after %.0f ms", elapsed_ms)
        with _LOCK:
            _STATE["status"] = "failed"
            _STATE["stages"] = stages
            _STATE["elapsed_ms"] = elapsed_ms
            _STATE["error"] = str(exc)

    return get_state()


def start_background_warmup() -> None:
    """Kick off warmup on a daemon thread so startup does not block.

    Queries issued before warmup finishes still succeed — they simply wait on
    the same loaders rather than duplicating the work.
    """
    global _THREAD

    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            LOGGER.info("Warmup already in progress; not starting a second run")
            return

    _THREAD = threading.Thread(target=run_warmup, name="securerag-warmup", daemon=True)
    _THREAD.start()
    LOGGER.info("Warmup started in background thread")

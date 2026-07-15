"""
Module 1.4 — EPSS Score Fetcher
==================================
Downloads EPSS (Exploit Prediction Scoring System) scores for all CVEs.
Uses the bulk CSV download (much faster than per-CVE API calls).

Primary: https://epss.cyentia.com/epss_scores-current.csv.gz (bulk CSV)
Fallback: https://api.first.org/data/v1/epss (paginated API)
"""

import csv
import gzip
import io
import json
import os
import sys
import time
import requests
from tqdm import tqdm

# ─── Configuration ───────────────────────────────────────────────
EPSS_CSV_URL = "https://epss.cyentia.com/epss_scores-current.csv.gz"
EPSS_API_URL = "https://api.first.org/data/v1/epss"
EPSS_API_LIMIT = 100  # records per API page

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_FILE = os.path.join(PROJECT_ROOT, "data", "raw", "epss_raw.json")
PROCESSED_FILE = os.path.join(PROJECT_ROOT, "data", "processed", "epss.json")


def download_epss_csv() -> list:
    """Download and parse the bulk EPSS CSV file (gzipped)."""
    print("→ Downloading EPSS bulk CSV (gzipped)...")
    print(f"  URL: {EPSS_CSV_URL}")

    resp = requests.get(EPSS_CSV_URL, timeout=120)
    resp.raise_for_status()

    download_size = len(resp.content) / (1024 ** 2)
    print(f"  ✓ Downloaded ({download_size:.1f} MB compressed)")

    # Decompress and parse
    print("→ Decompressing and parsing CSV...")
    decompressed = gzip.decompress(resp.content)
    text = decompressed.decode("utf-8")

    # The CSV has a comment header line starting with '#' — skip it
    lines = text.strip().split("\n")
    data_lines = []
    header_line = None

    for line in lines:
        if line.startswith("#"):
            # Model version / metadata comment
            print(f"  Metadata: {line.strip()}")
            continue
        if header_line is None:
            header_line = line
            continue
        data_lines.append(line)

    print(f"  CSV rows to parse: {len(data_lines):,}")

    # Parse CSV
    reader = csv.DictReader(io.StringIO(header_line + "\n" + "\n".join(data_lines)))
    records = []

    for row in reader:
        cve_id = row.get("cve", "").strip()
        epss_str = row.get("epss", "0").strip()
        percentile_str = row.get("percentile", "0").strip()

        if not cve_id:
            continue

        try:
            epss_val = float(epss_str)
        except ValueError:
            epss_val = 0.0

        try:
            percentile_val = float(percentile_str)
        except ValueError:
            percentile_val = 0.0

        records.append({
            "cve_id": cve_id,
            "epss_probability": round(epss_val, 6),
            "epss_percentile": round(percentile_val, 6),
        })

    return records


def fetch_epss_api_fallback() -> list:
    """Fallback: Fetch EPSS scores from the API with pagination."""
    print("→ Using API fallback for EPSS scores...")
    print(f"  URL: {EPSS_API_URL}")
    print("  ⚠ This is slower than the CSV download method")

    session = requests.Session()
    records = []
    offset = 0
    total = None

    pbar = None

    while True:
        params = {
            "limit": EPSS_API_LIMIT,
            "offset": offset,
        }

        try:
            resp = session.get(EPSS_API_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"\n  ⚠ Error at offset {offset}: {e}")
            time.sleep(2)
            continue

        if total is None:
            total = data.get("total", 0)
            print(f"  Total EPSS records available: {total:,}")
            pbar = tqdm(total=total, desc="Fetching EPSS", unit=" scores", ncols=100)

        api_data = data.get("data", [])
        if not api_data:
            break

        for item in api_data:
            records.append({
                "cve_id": item.get("cve", ""),
                "epss_probability": round(float(item.get("epss", 0)), 6),
                "epss_percentile": round(float(item.get("percentile", 0)), 6),
            })

        if pbar:
            pbar.update(len(api_data))

        offset += EPSS_API_LIMIT

        if offset >= total:
            break

        # Small delay to be polite
        time.sleep(0.2)

    if pbar:
        pbar.close()

    return records


def fetch_epss():
    """Main ingestion function for EPSS data."""
    print("=" * 60)
    print("  EPSS Score Fetcher — SecureRAG Phase 2")
    print("=" * 60)

    # Try CSV download first (much faster)
    try:
        records = download_epss_csv()
    except Exception as e:
        print(f"\n  ⚠ CSV download failed: {e}")
        print("  Falling back to API...")
        records = fetch_epss_api_fallback()

    if not records:
        print("  ✗ No EPSS records fetched!")
        sys.exit(1)

    # Save raw data
    print(f"\n→ Saving raw data ({len(records):,} records)...")
    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f)
    raw_size = os.path.getsize(RAW_FILE)
    print(f"  ✓ Raw data saved: {RAW_FILE} ({raw_size / (1024**2):.1f} MB)")

    # Processed data is the same structure — save with formatting
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    proc_size = os.path.getsize(PROCESSED_FILE)
    print(f"  ✓ Processed data saved: {PROCESSED_FILE} ({proc_size / (1024**2):.1f} MB)")

    # Summary statistics
    epss_values = [r["epss_probability"] for r in records]
    high_risk = [r for r in records if r["epss_probability"] >= 0.5]
    critical_risk = [r for r in records if r["epss_probability"] >= 0.9]

    print("\n" + "=" * 60)
    print(f"  EPSS Ingestion Complete!")
    print(f"  Total Scores: {len(records):,}")
    print(f"  EPSS Score Distribution:")
    print(f"    Very High (≥0.9):  {len(critical_risk):,}")
    print(f"    High (≥0.5):       {len(high_risk):,}")
    print(f"    Average Score:     {sum(epss_values) / len(epss_values):.6f}")
    print(f"    Max Score:         {max(epss_values):.6f}")
    print(f"    Min Score:         {min(epss_values):.6f}")
    print("=" * 60)

    return records


if __name__ == "__main__":
    fetch_epss()

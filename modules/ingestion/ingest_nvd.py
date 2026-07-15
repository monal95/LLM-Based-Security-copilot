"""
Module 1.1 — NVD CVE Ingestion
================================
Fetches all CVEs from the NVD API 2.0 using paginated requests.
Saves raw API responses to data/raw/nvd_raw.json and processed
records to data/processed/nvd.json.

Source: https://services.nvd.nist.gov/rest/json/cves/2.0
"""

import json
import os
import sys
import time
import re
import io
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime

# Fix Windows console encoding for Unicode characters
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ─── Configuration ───────────────────────────────────────────────
NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
RESULTS_PER_PAGE = 2000
API_KEY = os.environ.get("NVD_API_KEY", "dfad5476-a653-4482-85ba-d241509e6e88")

# Rate limiting: 50 req/30s with key → 0.7s delay; 5 req/30s without → 6.5s delay
REQUEST_DELAY = 0.7 if API_KEY else 6.5

# Paths (relative to project root)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_FILE = os.path.join(PROJECT_ROOT, "data", "raw", "nvd_raw.json")
PROCESSED_FILE = os.path.join(PROJECT_ROOT, "data", "processed", "nvd.json")
PAGES_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "nvd_pages")

MAX_RETRIES = 5
RETRY_BACKOFF = 2  # seconds, doubles each retry

thread_local = threading.local()

def get_session():
    """Get thread-local requests Session."""
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
    return thread_local.session


class SimpleRateLimiter:
    """Thread-safe rate limiter to enforce minimum interval between requests."""
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self.last_request_time = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_request_time = time.time()


def fetch_and_save_page(start_index: int, rate_limiter: SimpleRateLimiter) -> bool:
    """Fetch a single page and save it to a temporary file."""
    page_file = os.path.join(PAGES_DIR, f"page_{start_index}.json")
    if os.path.exists(page_file) and os.path.getsize(page_file) > 0:
        return True  # Already downloaded

    params = {
        "resultsPerPage": RESULTS_PER_PAGE,
        "startIndex": start_index,
    }
    headers = {}
    if API_KEY:
        headers["apiKey"] = API_KEY

    session = get_session()

    for attempt in range(MAX_RETRIES):
        try:
            # Enforce rate limit before calling the API
            rate_limiter.wait()
            
            resp = session.get(NVD_API_URL, params=params, headers=headers, timeout=120)

            if resp.status_code == 200:
                data = resp.json()
                # Write to temp file
                with open(page_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return True
            elif resp.status_code == 429:
                wait = RETRY_BACKOFF * (2 ** attempt)
                print(f"\n⚠ Rate limited (429) at startIndex={start_index}. Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
            elif resp.status_code == 503:
                wait = RETRY_BACKOFF * (2 ** attempt)
                print(f"\n⚠ Service unavailable (503) at startIndex={start_index}. Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
            else:
                print(f"\n✗ Unexpected status {resp.status_code} at startIndex={start_index}")
                resp.raise_for_status()

        except Exception as e:
            wait = RETRY_BACKOFF * (2 ** attempt)
            print(f"\n⚠ Error fetching page at startIndex={start_index}: {e}. Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
            time.sleep(wait)

    return False


def extract_cvss_info(metrics: dict) -> tuple:
    """Extract the best available CVSS score and severity from metrics."""
    # Try CVSS v3.1 first, then v3.0, then v2.0
    for version_key in ["cvssMetricV31", "cvssMetricV30"]:
        if version_key in metrics and metrics[version_key]:
            metric = metrics[version_key][0]  # Take the primary metric
            cvss_data = metric.get("cvssData", {})
            return (
                cvss_data.get("baseScore"),
                cvss_data.get("baseSeverity", "UNKNOWN").upper()
            )

    # Fallback to CVSS v2.0
    if "cvssMetricV2" in metrics and metrics["cvssMetricV2"]:
        metric = metrics["cvssMetricV2"][0]
        cvss_data = metric.get("cvssData", {})
        score = cvss_data.get("baseScore")
        # v2.0 doesn't have baseSeverity in the same place
        severity = metric.get("baseSeverity", "UNKNOWN").upper()
        return score, severity

    return None, "UNKNOWN"


def extract_affected_products(configurations: list) -> list:
    """Extract product names from CPE configurations."""
    products = set()
    for config in configurations:
        for node in config.get("nodes", []):
            for cpe_match in node.get("cpeMatch", []):
                criteria = cpe_match.get("criteria", "")
                # CPE format: cpe:2.3:a:vendor:product:version:...
                parts = criteria.split(":")
                if len(parts) >= 5:
                    vendor = parts[3]
                    product = parts[4]
                    if product != "*" and vendor != "*":
                        # Clean up underscores and capitalize
                        product_clean = product.replace("_", " ").title()
                        products.add(product_clean)
    return sorted(list(products))


def process_cve(vuln: dict) -> dict:
    """Process a single CVE vulnerability record."""
    cve = vuln.get("cve", {})

    # Extract CVE ID
    cve_id = cve.get("id", "")

    # Extract English description
    description = ""
    for desc in cve.get("descriptions", []):
        if desc.get("lang") == "en":
            description = desc.get("value", "")
            break

    # Extract CVSS info
    metrics = cve.get("metrics", {})
    cvss_score, severity = extract_cvss_info(metrics)

    # Extract affected products
    configurations = cve.get("configurations", [])
    affected_products = extract_affected_products(configurations)

    # Extract dates
    published = cve.get("published", "")
    last_modified = cve.get("lastModified", "")

    # Parse dates to YYYY-MM-DD format
    if published:
        try:
            published = published[:10]  # Take just the date part
        except (ValueError, IndexError):
            pass
    if last_modified:
        try:
            last_modified = last_modified[:10]
        except (ValueError, IndexError):
            pass

    return {
        "cve_id": cve_id,
        "description": description,
        "cvss_score": cvss_score,
        "severity": severity,
        "affected_products": affected_products,
        "published_date": published,
        "last_modified": last_modified,
    }


def fetch_all_cves():
    """Fetch all CVEs from the NVD API with pagination, parallel downloads, and page caching."""
    print("=" * 60)
    print("  NVD CVE Ingestion (Concurrent) — SecureRAG Phase 2")
    print("=" * 60)
    print(f"  API Key: {'Configured ✓' if API_KEY else 'Not set (slower rate limit)'}")
    print(f"  Request Delay: {REQUEST_DELAY}s between requests")
    print(f"  Results Per Page: {RESULTS_PER_PAGE}")
    print("=" * 60)

    os.makedirs(PAGES_DIR, exist_ok=True)

    # 1. Fetch page 0 to get total results
    first_page_file = os.path.join(PAGES_DIR, "page_0.json")
    total_results = None
    
    if os.path.exists(first_page_file):
        try:
            with open(first_page_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            total_results = data.get("totalResults", 0)
        except Exception:
            pass

    if total_results is None:
        print("\n→ Fetching initial page to determine total CVE count...")
        session = requests.Session()
        params = {"resultsPerPage": RESULTS_PER_PAGE, "startIndex": 0}
        headers = {"apiKey": API_KEY} if API_KEY else {}
        
        # Simple loop for the first page
        for attempt in range(MAX_RETRIES):
            try:
                resp = session.get(NVD_API_URL, params=params, headers=headers, timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    total_results = data.get("totalResults", 0)
                    with open(first_page_file, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                    break
                else:
                    time.sleep(2)
            except Exception as e:
                time.sleep(2)
        
        if total_results is None:
            raise RuntimeError("Failed to fetch initial page to determine total results.")

    print(f"  Total CVEs available: {total_results:,}")
    
    # 2. Determine all start indices
    start_indices = list(range(0, total_results, RESULTS_PER_PAGE))
    total_pages = len(start_indices)
    
    # Check which pages are already downloaded
    existing_pages = 0
    missing_indices = []
    for idx in start_indices:
        page_file = os.path.join(PAGES_DIR, f"page_{idx}.json")
        if os.path.exists(page_file) and os.path.getsize(page_file) > 0:
            existing_pages += 1
        else:
            missing_indices.append(idx)
            
    print(f"  Progress: {existing_pages}/{total_pages} pages already downloaded.")
    
    if missing_indices:
        print(f"  Downloading remaining {len(missing_indices)} pages...")
        rate_limiter = SimpleRateLimiter(REQUEST_DELAY)
        
        max_workers = 30 if API_KEY else 1
        
        pbar = tqdm(
            total=total_pages,
            initial=existing_pages,
            unit=" pages",
            desc="Downloading Pages",
            ncols=100
        )
        
        failed_indices = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(fetch_and_save_page, idx, rate_limiter): idx
                for idx in missing_indices
            }
            
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    success = future.result()
                    if not success:
                        failed_indices.append(idx)
                except Exception as e:
                    print(f"\n✗ Thread error for page {idx}: {e}")
                    failed_indices.append(idx)
                pbar.update(1)
        pbar.close()
        
        if failed_indices:
            print(f"\n⚠ Failed to download {len(failed_indices)} pages: {failed_indices}")
            print("Please re-run the script to retry downloading the failed pages.")
            sys.exit(1)
            
    # 3. Merge all page files into RAW_FILE
    print(f"\n→ Merging all {total_pages} page files into {RAW_FILE}...")
    raw_vulnerabilities = []
    for idx in tqdm(start_indices, desc="Merging", unit=" pages", ncols=100):
        page_file = os.path.join(PAGES_DIR, f"page_{idx}.json")
        with open(page_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_vulnerabilities.extend(data.get("vulnerabilities", []))
            
    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(raw_vulnerabilities, f)
        
    raw_size = os.path.getsize(RAW_FILE)
    print(f"  ✓ Raw data saved: {RAW_FILE} ({raw_size / (1024**3):.2f} GB)")
    
    # 4. Process and save to PROCESSED_FILE
    print(f"\n→ Processing {len(raw_vulnerabilities):,} CVEs...")
    processed = []
    for vuln in tqdm(raw_vulnerabilities, desc="Processing", unit=" CVEs", ncols=100):
        processed.append(process_cve(vuln))
        
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2)
        
    proc_size = os.path.getsize(PROCESSED_FILE)
    print(f"  ✓ Processed data saved: {PROCESSED_FILE} ({proc_size / (1024**2):.1f} MB)")
    
    # 5. Clean up the temporary page files
    print("\n→ Cleaning up temporary page files...")
    for idx in start_indices:
        page_file = os.path.join(PAGES_DIR, f"page_{idx}.json")
        if os.path.exists(page_file):
            try:
                os.remove(page_file)
            except Exception:
                pass
    try:
        os.rmdir(PAGES_DIR)
    except Exception:
        pass
    print("  ✓ Cleanup complete.")
    
    # ─── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  NVD Ingestion Complete!")
    print(f"  Total CVEs: {len(processed):,}")
    print(f"  With CVSS Score: {sum(1 for p in processed if p['cvss_score'] is not None):,}")
    print(f"  Severity Distribution:")
    severity_counts = {}
    for p in processed:
        sev = p.get("severity", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]:
        if sev in severity_counts:
            print(f"    {sev}: {severity_counts[sev]:,}")
    print("=" * 60)

    return processed


if __name__ == "__main__":
    fetch_all_cves()

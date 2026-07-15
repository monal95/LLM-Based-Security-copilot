"""
Module 1.3 — CISA KEV Ingestion
==================================
Downloads the CISA Known Exploited Vulnerabilities catalog
and extracts structured records.

Source: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
"""

import json
import os
import requests

# ─── Configuration ───────────────────────────────────────────────
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_FILE = os.path.join(PROJECT_ROOT, "data", "raw", "kev_raw.json")
PROCESSED_FILE = os.path.join(PROJECT_ROOT, "data", "processed", "kev.json")


def download_kev_catalog() -> dict:
    """Download the CISA KEV catalog."""
    print("→ Downloading CISA KEV catalog...")
    print(f"  URL: {KEV_URL}")

    resp = requests.get(KEV_URL, timeout=60)
    resp.raise_for_status()

    catalog = resp.json()
    vuln_count = len(catalog.get("vulnerabilities", []))
    print(f"  ✓ Downloaded ({len(resp.content) / 1024:.0f} KB, {vuln_count} vulnerabilities)")
    return catalog


def process_kev_entry(entry: dict) -> dict:
    """Process a single KEV vulnerability entry."""
    return {
        "cve_id": entry.get("cveID", ""),
        "vendor": entry.get("vendorProject", ""),
        "product": entry.get("product", ""),
        "vulnerability_name": entry.get("vulnerabilityName", ""),
        "date_added": entry.get("dateAdded", ""),
        "required_action": entry.get("requiredAction", ""),
        "due_date": entry.get("dueDate", ""),
        "known_ransomware_campaign_use": entry.get("knownRansomwareCampaignUse", "Unknown"),
        "short_description": entry.get("shortDescription", ""),
        "notes": entry.get("notes", ""),
    }


def ingest_kev():
    """Main ingestion function for CISA KEV data."""
    print("=" * 60)
    print("  CISA KEV Ingestion — SecureRAG Phase 2")
    print("=" * 60)

    # Download
    catalog = download_kev_catalog()

    # Save raw data
    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f)
    raw_size = os.path.getsize(RAW_FILE)
    print(f"  ✓ Raw data saved: {RAW_FILE} ({raw_size / 1024:.0f} KB)")

    # Process
    vulnerabilities = catalog.get("vulnerabilities", [])
    print(f"\n→ Processing {len(vulnerabilities)} KEV entries...")

    processed = []
    for entry in vulnerabilities:
        processed.append(process_kev_entry(entry))

    # Sort by date_added (most recent first)
    processed.sort(key=lambda x: x.get("date_added", ""), reverse=True)

    # Save processed data
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2)
    proc_size = os.path.getsize(PROCESSED_FILE)
    print(f"  ✓ Processed data saved: {PROCESSED_FILE} ({proc_size / 1024:.0f} KB)")

    # Summary
    ransomware_yes = sum(1 for p in processed if p.get("known_ransomware_campaign_use") == "Known")
    vendors = set(p.get("vendor") for p in processed)

    print("\n" + "=" * 60)
    print(f"  CISA KEV Ingestion Complete!")
    print(f"  Total KEV Entries: {len(processed)}")
    print(f"  Unique Vendors: {len(vendors)}")
    print(f"  Known Ransomware Campaign Use: {ransomware_yes}")
    print(f"  Date Range: {processed[-1].get('date_added', 'N/A')} → {processed[0].get('date_added', 'N/A')}")

    # Top 10 vendors
    vendor_counts = {}
    for p in processed:
        v = p.get("vendor", "Unknown")
        vendor_counts[v] = vendor_counts.get(v, 0) + 1
    top_vendors = sorted(vendor_counts.items(), key=lambda x: -x[1])[:10]
    print(f"  Top 10 Vendors:")
    for vendor, count in top_vendors:
        print(f"    {vendor}: {count}")
    print("=" * 60)

    return processed


if __name__ == "__main__":
    ingest_kev()

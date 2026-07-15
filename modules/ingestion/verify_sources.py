"""
Verification Script — verify_sources.py
==========================================
Loads all four processed CTI JSON files and validates data integrity.
Prints summary counts and runs basic consistency checks.
"""

import json
import os
import re
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")

# Expected files
FILES = {
    "nvd": os.path.join(PROCESSED_DIR, "nvd.json"),
    "mitre": os.path.join(PROCESSED_DIR, "mitre.json"),
    "kev": os.path.join(PROCESSED_DIR, "kev.json"),
    "epss": os.path.join(PROCESSED_DIR, "epss.json"),
}

CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,}$")


def load_json(filepath: str) -> list:
    """Load a JSON file and return its contents."""
    if not os.path.exists(filepath):
        print(f"  ✗ File not found: {filepath}")
        return []

    file_size = os.path.getsize(filepath)
    if file_size == 0:
        print(f"  ✗ File is empty: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    return []


def verify_nvd(data: list) -> bool:
    """Verify NVD data integrity."""
    errors = []

    # Check for duplicates
    cve_ids = [r.get("cve_id") for r in data]
    unique_ids = set(cve_ids)
    if len(cve_ids) != len(unique_ids):
        errors.append(f"  ⚠ {len(cve_ids) - len(unique_ids)} duplicate CVE IDs found")

    # Validate CVE ID format
    invalid_ids = [cid for cid in cve_ids if cid and not CVE_PATTERN.match(cid)]
    if invalid_ids:
        errors.append(f"  ⚠ {len(invalid_ids)} invalid CVE ID formats (e.g., {invalid_ids[0]})")

    # Validate CVSS scores
    for r in data:
        score = r.get("cvss_score")
        if score is not None and (score < 0 or score > 10):
            errors.append(f"  ⚠ Invalid CVSS score {score} for {r.get('cve_id')}")

    # Check for known CVEs
    known_cves = {"CVE-2021-44228", "CVE-2017-0144", "CVE-2014-0160"}
    found_known = known_cves.intersection(unique_ids)
    if found_known:
        print(f"  ✓ Known CVEs found: {', '.join(sorted(found_known))}")

    # Spot check a known CVE
    log4shell = next((r for r in data if r.get("cve_id") == "CVE-2021-44228"), None)
    if log4shell:
        print(f"  ✓ Sample — CVE-2021-44228 (Log4Shell):")
        print(f"    CVSS: {log4shell.get('cvss_score')}, Severity: {log4shell.get('severity')}")
        print(f"    Description: {log4shell.get('description', '')[:100]}...")

    for err in errors:
        print(err)

    return len(errors) == 0


def verify_mitre(data: list) -> bool:
    """Verify MITRE ATT&CK data integrity."""
    errors = []

    # Check for duplicates
    tech_ids = [r.get("technique_id") for r in data]
    unique_ids = set(tech_ids)
    if len(tech_ids) != len(unique_ids):
        errors.append(f"  ⚠ {len(tech_ids) - len(unique_ids)} duplicate technique IDs")

    # Validate technique ID format
    invalid_ids = [tid for tid in tech_ids if tid and not re.match(r"^T\d{4}(\.\d{3})?$", tid)]
    if invalid_ids:
        errors.append(f"  ⚠ {len(invalid_ids)} invalid technique ID formats")

    # Check for T1059 (Command and Scripting Interpreter)
    t1059 = next((r for r in data if r.get("technique_id") == "T1059"), None)
    if t1059:
        print(f"  ✓ Sample — T1059 ({t1059.get('name')}):")
        print(f"    Tactics: {t1059.get('tactics')}")
        print(f"    Platforms: {t1059.get('platforms')}")
        print(f"    Sub-techniques: {len(t1059.get('sub_techniques', []))}")

    parent_count = sum(1 for t in data if "." not in t.get("technique_id", ""))
    sub_count = sum(1 for t in data if "." in t.get("technique_id", ""))
    print(f"  ✓ Parent techniques: {parent_count}, Sub-techniques: {sub_count}")

    for err in errors:
        print(err)

    return len(errors) == 0


def verify_kev(data: list) -> bool:
    """Verify CISA KEV data integrity."""
    errors = []

    # Check for duplicates
    cve_ids = [r.get("cve_id") for r in data]
    unique_ids = set(cve_ids)
    if len(cve_ids) != len(unique_ids):
        errors.append(f"  ⚠ {len(cve_ids) - len(unique_ids)} duplicate CVE IDs")

    # Validate CVE ID format
    invalid_ids = [cid for cid in cve_ids if cid and not CVE_PATTERN.match(cid)]
    if invalid_ids:
        errors.append(f"  ⚠ {len(invalid_ids)} invalid CVE ID formats")

    # Check for MOVEit (CVE-2023-34362)
    moveit = next((r for r in data if r.get("cve_id") == "CVE-2023-34362"), None)
    if moveit:
        print(f"  ✓ Sample — CVE-2023-34362 (MOVEit):")
        print(f"    Vendor: {moveit.get('vendor')}, Product: {moveit.get('product')}")
        print(f"    Ransomware: {moveit.get('known_ransomware_campaign_use')}")

    ransomware_count = sum(1 for r in data if r.get("known_ransomware_campaign_use") == "Known")
    print(f"  ✓ KEV entries with known ransomware use: {ransomware_count}")

    for err in errors:
        print(err)

    return len(errors) == 0


def verify_epss(data: list) -> bool:
    """Verify EPSS data integrity."""
    errors = []

    # Check for duplicates
    cve_ids = [r.get("cve_id") for r in data]
    unique_ids = set(cve_ids)
    if len(cve_ids) != len(unique_ids):
        errors.append(f"  ⚠ {len(cve_ids) - len(unique_ids)} duplicate CVE IDs")

    # Validate EPSS probability range
    out_of_range = []
    for r in data:
        prob = r.get("epss_probability", 0)
        if prob < 0 or prob > 1:
            out_of_range.append(r.get("cve_id"))
    if out_of_range:
        errors.append(f"  ⚠ {len(out_of_range)} EPSS probabilities out of range [0, 1]")

    # Check for Log4Shell EPSS
    log4shell = next((r for r in data if r.get("cve_id") == "CVE-2021-44228"), None)
    if log4shell:
        print(f"  ✓ Sample — CVE-2021-44228 (Log4Shell):")
        print(f"    EPSS Probability: {log4shell.get('epss_probability')}")
        print(f"    EPSS Percentile: {log4shell.get('epss_percentile')}")

    # High risk stats
    high_risk = sum(1 for r in data if r.get("epss_probability", 0) >= 0.5)
    print(f"  ✓ High-risk CVEs (EPSS ≥ 0.5): {high_risk}")

    for err in errors:
        print(err)

    return len(errors) == 0


def verify_cross_source(nvd_data: list, kev_data: list, epss_data: list):
    """Cross-validate data between sources."""
    print("\n─── Cross-Source Validation ────────────────────────────────")

    nvd_cves = set(r.get("cve_id") for r in nvd_data)
    kev_cves = set(r.get("cve_id") for r in kev_data)
    epss_cves = set(r.get("cve_id") for r in epss_data)

    # KEV entries that are in NVD
    kev_in_nvd = kev_cves.intersection(nvd_cves)
    print(f"  KEV entries found in NVD: {len(kev_in_nvd)}/{len(kev_cves)}")

    # KEV entries that have EPSS scores
    kev_in_epss = kev_cves.intersection(epss_cves)
    print(f"  KEV entries with EPSS scores: {len(kev_in_epss)}/{len(kev_cves)}")

    # NVD CVEs with EPSS scores
    nvd_in_epss = nvd_cves.intersection(epss_cves)
    print(f"  NVD CVEs with EPSS scores: {len(nvd_in_epss)}/{len(nvd_cves)}")


def main():
    """Main verification function."""
    print("=" * 60)
    print("  SecureRAG CTI Knowledge Base — Verification")
    print("=" * 60)

    all_passed = True
    datasets = {}

    for name, filepath in FILES.items():
        print(f"\n─── {name.upper()} ────────────────────────────────────────────")
        data = load_json(filepath)
        datasets[name] = data

        if not data:
            all_passed = False
            continue

        # File size
        file_size = os.path.getsize(filepath)
        if file_size > 1024 ** 3:
            size_str = f"{file_size / (1024**3):.2f} GB"
        elif file_size > 1024 ** 2:
            size_str = f"{file_size / (1024**2):.1f} MB"
        else:
            size_str = f"{file_size / 1024:.0f} KB"
        print(f"  File size: {size_str}")

        # Run specific verification
        if name == "nvd":
            print(f"  NVD CVEs Loaded: {len(data)}")
            if not verify_nvd(data):
                all_passed = False
        elif name == "mitre":
            print(f"  MITRE Techniques Loaded: {len(data)}")
            if not verify_mitre(data):
                all_passed = False
        elif name == "kev":
            print(f"  KEV Entries Loaded: {len(data)}")
            if not verify_kev(data):
                all_passed = False
        elif name == "epss":
            print(f"  EPSS Scores Loaded: {len(data)}")
            if not verify_epss(data):
                all_passed = False

    # Cross-source validation
    if all(datasets.get(k) for k in ["nvd", "kev", "epss"]):
        verify_cross_source(datasets["nvd"], datasets["kev"], datasets["epss"])

    # Final summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  NVD CVEs Loaded:         {len(datasets.get('nvd', []))}")
    print(f"  MITRE Techniques Loaded: {len(datasets.get('mitre', []))}")
    print(f"  KEV Entries Loaded:      {len(datasets.get('kev', []))}")
    print(f"  EPSS Scores Loaded:      {len(datasets.get('epss', []))}")
    print("=" * 60)

    if all_passed and all(datasets.get(k) for k in FILES):
        print("  ✓ All sources verified successfully!")
    else:
        print("  ⚠ Some verifications failed or data is missing.")
        print("    Run the individual ingestion scripts first.")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

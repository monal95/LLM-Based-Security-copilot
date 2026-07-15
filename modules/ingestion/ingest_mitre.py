"""
Module 1.2 — MITRE ATT&CK Ingestion
======================================
Downloads the MITRE ATT&CK Enterprise STIX 2.1 bundle and extracts
technique records with tactics, mitigations, platforms, and data sources.

Source: https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json
"""

import json
import os
import sys
import requests
from tqdm import tqdm

# ─── Configuration ───────────────────────────────────────────────
MITRE_STIX_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
    "master/enterprise-attack/enterprise-attack.json"
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_FILE = os.path.join(PROJECT_ROOT, "data", "raw", "mitre_raw.json")
PROCESSED_FILE = os.path.join(PROJECT_ROOT, "data", "processed", "mitre.json")


def download_stix_bundle() -> dict:
    """Download the MITRE ATT&CK STIX 2.1 bundle."""
    print("→ Downloading MITRE ATT&CK Enterprise STIX bundle...")
    print(f"  URL: {MITRE_STIX_URL}")

    resp = requests.get(MITRE_STIX_URL, timeout=120)
    resp.raise_for_status()

    bundle = resp.json()
    print(f"  ✓ Downloaded ({len(resp.content) / (1024**2):.1f} MB)")
    print(f"  STIX Objects: {len(bundle.get('objects', []))}")
    return bundle


def build_lookup_maps(objects: list) -> tuple:
    """Build lookup maps for mitigations and relationships."""
    # Map STIX IDs to mitigation names
    mitigations_map = {}
    # Map technique STIX IDs to their mitigation names via relationships
    technique_mitigations = {}
    # Map parent technique IDs to sub-technique IDs
    sub_technique_map = {}

    # First pass: index mitigations (course-of-action)
    for obj in objects:
        if obj.get("type") == "course-of-action":
            if obj.get("revoked") or obj.get("x_mitre_deprecated"):
                continue
            stix_id = obj.get("id", "")
            name = obj.get("name", "")
            # Get the MITRE ID (e.g., M1036)
            mitre_id = ""
            for ref in obj.get("external_references", []):
                if ref.get("source_name") == "mitre-attack":
                    mitre_id = ref.get("external_id", "")
                    break
            mitigations_map[stix_id] = {
                "mitigation_id": mitre_id,
                "name": name,
            }

    # Second pass: index relationships (mitigates)
    for obj in objects:
        if obj.get("type") != "relationship":
            continue
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        rel_type = obj.get("relationship_type", "")
        source = obj.get("source_ref", "")
        target = obj.get("target_ref", "")

        if rel_type == "mitigates" and source in mitigations_map:
            if target not in technique_mitigations:
                technique_mitigations[target] = []
            technique_mitigations[target].append(mitigations_map[source])

        # Track sub-technique relationships
        if rel_type == "subtechnique-of":
            if target not in sub_technique_map:
                sub_technique_map[target] = []
            sub_technique_map[target].append(source)

    return mitigations_map, technique_mitigations, sub_technique_map


def format_tactic_name(phase_name: str) -> str:
    """Convert kill chain phase name to title case (e.g., 'initial-access' → 'Initial Access')."""
    return phase_name.replace("-", " ").title()


def extract_technique(obj: dict, technique_mitigations: dict, stix_id_to_technique_id: dict, sub_technique_map: dict) -> dict:
    """Extract a technique record from a STIX attack-pattern object."""
    # Get technique ID (e.g., T1059)
    technique_id = ""
    url = ""
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            technique_id = ref.get("external_id", "")
            url = ref.get("url", "")
            break

    # Get tactics from kill chain phases
    tactics = []
    for phase in obj.get("kill_chain_phases", []):
        if phase.get("kill_chain_name") == "mitre-attack":
            tactics.append(format_tactic_name(phase.get("phase_name", "")))

    # Get mitigations for this technique
    stix_id = obj.get("id", "")
    mitigations = technique_mitigations.get(stix_id, [])

    # Get sub-techniques
    sub_techniques = []
    for sub_stix_id in sub_technique_map.get(stix_id, []):
        sub_tid = stix_id_to_technique_id.get(sub_stix_id)
        if sub_tid:
            sub_techniques.append(sub_tid)
    sub_techniques.sort()

    return {
        "technique_id": technique_id,
        "name": obj.get("name", ""),
        "description": obj.get("description", ""),
        "tactics": tactics,
        "sub_techniques": sub_techniques,
        "mitigations": mitigations,
        "platforms": obj.get("x_mitre_platforms", []),
        "data_sources": obj.get("x_mitre_data_sources", []),
        "url": url,
    }


def process_stix_bundle(bundle: dict) -> list:
    """Process the STIX bundle and extract all technique records."""
    objects = bundle.get("objects", [])

    print(f"\n→ Processing {len(objects)} STIX objects...")

    # Build lookup maps
    mitigations_map, technique_mitigations, sub_technique_map = build_lookup_maps(objects)

    # Build STIX ID → technique ID map for sub-technique resolution
    stix_id_to_technique_id = {}
    attack_patterns = []

    for obj in objects:
        if obj.get("type") != "attack-pattern":
            continue
        # Skip revoked or deprecated techniques
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue

        stix_id = obj.get("id", "")
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                stix_id_to_technique_id[stix_id] = ref.get("external_id", "")
                break

        attack_patterns.append(obj)

    print(f"  Found {len(attack_patterns)} active techniques/sub-techniques")
    print(f"  Found {len(mitigations_map)} mitigations")
    print(f"  Found {len(technique_mitigations)} technique-mitigation relationships")

    # Extract techniques
    techniques = []
    for obj in tqdm(attack_patterns, desc="Extracting techniques", unit=" techniques", ncols=100):
        technique = extract_technique(obj, technique_mitigations, stix_id_to_technique_id, sub_technique_map)
        techniques.append(technique)

    # Sort by technique ID
    techniques.sort(key=lambda t: t["technique_id"])

    return techniques


def ingest_mitre():
    """Main ingestion function for MITRE ATT&CK data."""
    print("=" * 60)
    print("  MITRE ATT&CK Ingestion — SecureRAG Phase 2")
    print("=" * 60)

    # Download
    bundle = download_stix_bundle()

    # Save raw data
    os.makedirs(os.path.dirname(RAW_FILE), exist_ok=True)
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(bundle, f)
    raw_size = os.path.getsize(RAW_FILE)
    print(f"  ✓ Raw data saved: {RAW_FILE} ({raw_size / (1024**2):.1f} MB)")

    # Process
    techniques = process_stix_bundle(bundle)

    # Save processed data
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(techniques, f, indent=2)
    proc_size = os.path.getsize(PROCESSED_FILE)
    print(f"  ✓ Processed data saved: {PROCESSED_FILE} ({proc_size / (1024**2):.1f} MB)")

    # Summary
    parent_techniques = [t for t in techniques if "." not in t["technique_id"]]
    sub_techniques = [t for t in techniques if "." in t["technique_id"]]

    print("\n" + "=" * 60)
    print(f"  MITRE ATT&CK Ingestion Complete!")
    print(f"  Total Techniques: {len(techniques)}")
    print(f"    Parent Techniques: {len(parent_techniques)}")
    print(f"    Sub-Techniques: {len(sub_techniques)}")

    # Tactic distribution
    tactic_counts = {}
    for t in techniques:
        for tac in t["tactics"]:
            tactic_counts[tac] = tactic_counts.get(tac, 0) + 1
    print(f"  Tactics Coverage:")
    for tac, count in sorted(tactic_counts.items(), key=lambda x: -x[1]):
        print(f"    {tac}: {count}")
    print("=" * 60)

    return techniques


if __name__ == "__main__":
    ingest_mitre()

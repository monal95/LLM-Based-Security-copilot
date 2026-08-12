"""Generator script for SecureRAG Phase 6 300-query evaluation dataset.

Generates:
  evaluation/phase6_queries.json (300 queries: 100 CVE, 100 ATT&CK, 100 IR)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_FILE = PROJECT_ROOT / "evaluation" / "phase6_queries.json"

LOGGER = logging.getLogger(__name__)


def load_processed_data():
    kev_path = DATA_DIR / "kev.json"
    mitre_path = DATA_DIR / "mitre.json"
    nvd_path = DATA_DIR / "nvd.json"

    with open(kev_path, "r", encoding="utf-8") as f:
        kev = json.load(f)
    with open(mitre_path, "r", encoding="utf-8") as f:
        mitre = json.load(f)

    with open(nvd_path, "r", encoding="utf-8") as f:
        nvd_raw = json.load(f)
        nvd = {item["cve_id"].upper(): item for item in nvd_raw if isinstance(item, dict) and "cve_id" in item}

    return kev, mitre, nvd


def generate_cve_queries(kev: List[Dict[str, Any]], nvd: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    queries = []

    curated_cves = [
        ("CVE-2021-44228", "Log4Shell RCE in Apache Log4j", "easy"),
        ("CVE-2017-0144", "EternalBlue SMBv1 remote code execution", "easy"),
        ("CVE-2020-1472", "Zerologon Netlogon privilege escalation", "easy"),
        ("CVE-2021-34527", "PrintNightmare Windows Print Spooler RCE", "easy"),
        ("CVE-2014-0160", "Heartbleed OpenSSL TLS heartbeat extension leak", "easy"),
        ("CVE-2021-26855", "ProxyLogon Microsoft Exchange SSRF", "easy"),
        ("CVE-2019-0708", "BlueKeep RDP Remote Code Execution", "easy"),
        ("CVE-2022-30190", "Follina Microsoft Support Diagnostic Tool MSDT RCE", "easy"),
        ("CVE-2023-23397", "Microsoft Outlook Elevation of Privilege via NTLM", "easy"),
        ("CVE-2021-40444", "Microsoft Office MSHTML Remote Code Execution", "easy"),
        ("CVE-2023-34362", "MOVEit Transfer SQL Injection Remote Code Execution", "medium"),
        ("CVE-2018-13379", "Fortinet FortiOS SSL VPN Path Traversal", "medium"),
        ("CVE-2019-11510", "Pulse Secure VPN Arbitrary File Read", "medium"),
        ("CVE-2019-19781", "Citrix ADC and Gateway Directory Traversal RCE", "medium"),
        ("CVE-2020-5902", "F5 BIG-IP TMUI Remote Code Execution", "medium"),
        ("CVE-2021-26084", "Atlassian Confluence OGNL Injection RCE", "medium"),
        ("CVE-2017-5638", "Apache Struts2 Jakarta Multipart Parser RCE", "medium"),
        ("CVE-2021-21972", "VMware vCenter Server Remote Code Execution", "medium"),
        ("CVE-2023-0669", "Fortra GoAnywhere MFT Command Injection", "medium"),
        ("CVE-2022-41040", "ProxyNotShell Microsoft Exchange SSRF", "medium"),
    ]

    for idx, (cve_id, desc, diff) in enumerate(curated_cves, start=1):
        nvd_rec = nvd.get(cve_id, {})
        kev_rec = next((item for item in kev if item.get("cve_id", "").upper() == cve_id), {})

        cvss = nvd_rec.get("cvss_score", "10.0")
        short_desc = kev_rec.get("short_description") or nvd_rec.get("description") or desc
        vendor = kev_rec.get("vendor") or "Affected Vendor"
        product = kev_rec.get("product") or "Affected Product"

        gt_answer = (
            f"{cve_id} is a critical vulnerability in {vendor} {product}. "
            f"CVSS Score: {cvss}. Description: {short_desc}. "
            f"Known Exploited Status: {'Yes (CISA KEV)' if kev_rec else 'No'}."
        )

        query_templates = [
            f"What is {cve_id}?",
            f"Explain {cve_id} vulnerability details and CVSS score.",
            f"What is the impact and severity of {cve_id}?",
            f"Provide a threat intelligence summary for {cve_id}.",
            f"What affected systems and products are tied to {cve_id}?",
        ]
        q_text = query_templates[(idx - 1) % len(query_templates)]

        queries.append({
            "id": f"CVE_{idx:03d}",
            "category": "cve_explanation",
            "query": q_text,
            "expected_documents": [cve_id],
            "ground_truth_answer": gt_answer,
            "ground_truth_entities": [cve_id],
            "ground_truth_techniques": [],
            "difficulty": diff,
        })

    seen_cves = {q["expected_documents"][0] for q in queries}
    count = len(queries) + 1

    for item in kev:
        if count > 100:
            break
        cve_id = item.get("cve_id", "").upper()
        if not cve_id or cve_id in seen_cves:
            continue

        nvd_rec = nvd.get(cve_id, {})
        cvss = nvd_rec.get("cvss_score", 7.5)
        vendor = item.get("vendor", "")
        product = item.get("product", "")
        short_desc = item.get("short_description") or nvd_rec.get("description") or f"Vulnerability affecting {vendor} {product}."
        action = item.get("required_action", "Apply vendor updates immediately.")

        gt_answer = (
            f"{cve_id} affects {vendor} {product}. "
            f"CVSS score: {cvss}. Description: {short_desc} "
            f"CISA KEV Required Action: {action}"
        )

        q_templates = [
            f"Details on {cve_id} vulnerability.",
            f"Explain the technical impact of {cve_id}.",
            f"What is the CISA KEV status and required action for {cve_id}?",
            f"How severe is {cve_id} affecting {vendor} {product}?",
            f"What is {cve_id} and what mitigation is required?",
        ]
        q_text = q_templates[(count - 1) % len(q_templates)]

        queries.append({
            "id": f"CVE_{count:03d}",
            "category": "cve_explanation",
            "query": q_text,
            "expected_documents": [cve_id],
            "ground_truth_answer": gt_answer,
            "ground_truth_entities": [cve_id],
            "ground_truth_techniques": [],
            "difficulty": "medium" if count <= 60 else "hard",
        })
        seen_cves.add(cve_id)
        count += 1

    return queries


def generate_mitre_queries(mitre: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queries = []

    for idx, item in enumerate(mitre[:100], start=1):
        tech_id = item.get("technique_id", f"T{1000+idx}").upper()
        name = item.get("name", "Unknown Technique")
        desc = item.get("description", "No description provided.")
        tactics = item.get("tactics", ["Execution"])
        tactics_str = ", ".join(tactics) if tactics else "General ATT&CK Tactic"

        gt_answer = (
            f"MITRE ATT&CK technique {tech_id} ({name}) belongs to tactic(s): {tactics_str}. "
            f"Description: {desc[:300]}..."
        )

        q_templates = [
            f"Explain MITRE ATT&CK technique {tech_id}.",
            f"What is {tech_id} ({name}) in MITRE ATT&CK?",
            f"How does adversaries execute technique {tech_id}?",
            f"What tactic is associated with MITRE technique {tech_id}?",
            f"Provide a description and mitigations for {tech_id} ({name}).",
        ]
        q_text = q_templates[(idx - 1) % len(q_templates)]

        difficulty = "easy" if idx <= 35 else ("medium" if idx <= 75 else "hard")

        queries.append({
            "id": f"ATTACK_{idx:03d}",
            "category": "mitre_mapping",
            "query": q_text,
            "expected_documents": [tech_id],
            "ground_truth_answer": gt_answer,
            "ground_truth_entities": [tech_id],
            "ground_truth_techniques": [tech_id],
            "difficulty": difficulty,
        })

    return queries


def generate_ir_queries(kev: List[Dict[str, Any]], mitre: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queries = []
    seen_query_texts = set()

    kev_cves = [item.get("cve_id", "").upper() for item in kev[:50] if item.get("cve_id")]
    mitre_techs = [item.get("technique_id", "").upper() for item in mitre[:50] if item.get("technique_id")]

    actions = [
        "initial containment steps",
        "forensic triage procedure",
        "eradication protocol",
        "recovery workflow",
        "evidence preservation checklist",
        "notification sequence per NIST CSF 2.0",
        "threat hunting rule definition",
        "SIEM log analysis strategy",
        "EDR isolation playbook",
        "patch prioritization priority",
    ]

    count = 1
    for i in range(100):
        cve_ref = kev_cves[i % len(kev_cves)]
        tech_ref = mitre_techs[i % len(mitre_techs)]
        action = actions[i % len(actions)]

        # Unique query template combinations
        if i < 20:
            q_text = f"What are the mandatory {action} when responding to an active security incident exploiting {cve_ref}?"
        elif i < 40:
            q_text = f"How should a SOC analyst execute {action} for an intrusion utilizing MITRE ATT&CK technique {tech_ref}?"
        elif i < 60:
            q_text = f"Provide a step-by-step NIST CSF 2.0 incident response guide covering {action} for {cve_ref}."
        elif i < 80:
            q_text = f"What is the SOC playbook for {action} during an ongoing attack involving {tech_ref} and {cve_ref}?"
        else:
            q_text = f"Explain the recommended {action} to neutralize threat activity linked to {cve_ref}."

        if q_text.lower() in seen_query_texts:
            q_text = f"Incident response protocol #{i+1}: What is the recommended {action} for threat actor activity exploiting {cve_ref} via {tech_ref}?"

        seen_query_texts.add(q_text.lower())

        gt_answer = (
            f"NIST CSF 2.0 Incident Response Guide for {cve_ref} / {tech_ref}: "
            f"1. Containment: Isolate host, block IOC IPs, revoke compromised user tokens. "
            f"2. Eradication: Remove malicious processes, delete unauthorized web shells, patch {cve_ref}. "
            f"3. Recovery: Restore endpoints from clean system backups and enforce MFA. "
            f"4. Evidence Preservation: Capture volatile RAM, dump disk images, preserve SIEM audit logs. "
            f"5. Notification: Escalate incident to CISO, legal, and compliance teams."
        )

        diff = "easy" if count <= 30 else ("medium" if count <= 70 else "hard")

        queries.append({
            "id": f"IR_{count:03d}",
            "category": "incident_response",
            "query": q_text,
            "expected_documents": [cve_ref],
            "ground_truth_answer": gt_answer,
            "ground_truth_entities": [cve_ref],
            "ground_truth_techniques": [tech_ref],
            "difficulty": diff,
        })
        count += 1

    return queries


def main():
    logging.basicConfig(level=logging.INFO)
    LOGGER.info("Loading processed datasets for ground truth construction...")
    kev, mitre, nvd = load_processed_data()

    cve_queries = generate_cve_queries(kev, nvd)
    mitre_queries = generate_mitre_queries(mitre)
    ir_queries = generate_ir_queries(kev, mitre)

    total_queries = cve_queries + mitre_queries + ir_queries

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(total_queries, f, indent=2)

    LOGGER.info(
        "Generated %d total queries (%d CVE, %d ATT&CK, %d IR) -> %s",
        len(total_queries),
        len(cve_queries),
        len(mitre_queries),
        len(ir_queries),
        OUTPUT_FILE,
    )


if __name__ == "__main__":
    main()

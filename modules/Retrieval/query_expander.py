"""SecureRAG Module 3.5 - Query Expansion.

Expands cybersecurity analyst queries with domain synonyms, vulnerability nicknames,
and associated CVE identifiers to increase retrieval recall.

Public API:
    expand_query(query: str) -> List[str]
"""

from __future__ import annotations

import re
from typing import Dict, List

# Static cybersecurity domain synonym expansion mapping
CYBER_SYNONYM_MAP: Dict[str, List[str]] = {
    "log4shell": ["Log4Shell", "Apache Log4j", "CVE-2021-44228", "CVE-2021-45046", "JNDI RCE"],
    "log4j": ["Log4Shell", "Apache Log4j", "CVE-2021-44228", "CVE-2021-45046"],
    "eternalblue": ["EternalBlue", "MS17-010", "CVE-2017-0144", "SMBv1 RCE"],
    "zerologon": ["Zerologon", "CVE-2020-1472", "Netlogon privilege escalation"],
    "printnightmare": ["PrintNightmare", "CVE-2021-34527", "Windows Print Spooler"],
    "proxyshell": ["ProxyShell", "CVE-2021-34473", "CVE-2021-34523", "CVE-2021-31207", "Microsoft Exchange"],
    "heartbleed": ["Heartbleed", "CVE-2014-0160", "OpenSSL"],
    "follina": ["Follina", "CVE-2022-30190", "MSDT"],
    "bluekeep": ["BlueKeep", "CVE-2019-0708", "RDP RCE"],
    "moveit": ["MOVEit Transfer", "CVE-2023-34362", "SQL Injection"],
    "curvetest": ["CurveBall", "CVE-2020-0601", "CryptoAPI"],
    "hivenightmare": ["HiveNightmare", "SeriousSam", "CVE-2021-36934"],
}


def expand_query(query: str) -> List[str]:
    """Expand input query text into a list of search query variations.

    Args:
        query: Analyst input query string.

    Returns:
        List of expanded query variations, starting with the original query.
    """
    normalized = query.strip()
    if not normalized:
        return [query]

    expanded: List[str] = [normalized]
    lowered = normalized.lower()

    for keyword, synonyms in CYBER_SYNONYM_MAP.items():
        if keyword in lowered:
            for syn in synonyms:
                if syn.lower() not in lowered and syn not in expanded:
                    expanded.append(syn)

    return expanded

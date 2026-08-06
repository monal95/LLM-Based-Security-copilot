"""Module 2.1 - CTI chunking for SecureRAG.

This module streams the processed CTI JSON artifacts generated in Module 1,
creates one document per security record, chunks each document with a
Tokenizer-aware RecursiveCharacterTextSplitter, and persists the result to
``data/chunks/chunks.json``.

The implementation is batch-oriented and resumable. It does not hold all
records or chunks in memory at once, and it checkpoints after every completed
batch so interrupted runs can resume safely.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import re
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:  # pragma: no cover - compatibility fallback
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore

from tqdm import tqdm


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "data" / "chunks"
OUTPUT_FILE = OUTPUT_DIR / "chunks.json"
CHECKPOINT_FILE = OUTPUT_DIR / "chunker_checkpoint.json"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SOURCE_ORDER = ("nvd", "mitre", "kev")


@dataclass(slots=True)
class ChunkerConfig:
    """Runtime configuration for CTI chunking."""

    processed_dir: Path = PROCESSED_DIR
    output_file: Path = OUTPUT_FILE
    checkpoint_file: Path = CHECKPOINT_FILE
    chunk_size: int = 512
    chunk_overlap: int = 50
    tokenizer_name: str = EMBEDDING_MODEL_NAME
    chunk_batch_size: int = 1000
    progress_refresh_interval: float = 0.5


@dataclass(slots=True)
class ChunkerCheckpoint:
    """Persistent resume state for the chunking pipeline."""

    source_name: str
    next_record_index: int
    chunks_written: int
    file_position: int
    complete: bool = False


class _TqdmLoggingHandler(logging.Handler):
    """Route log messages through tqdm so bars remain readable."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            tqdm.write(message)
        except Exception:  # pragma: no cover - logging should never crash work
            self.handleError(record)


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    handler = _TqdmLoggingHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def _stream_json_array(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield objects from a JSON array without loading the entire file."""

    decoder = json.JSONDecoder()
    buffer = ""
    inside_array = False

    with path.open("r", encoding="utf-8") as handle:
        while True:
            chunk = handle.read(65536)
            if chunk:
                buffer += chunk
            elif not buffer:
                break

            while True:
                buffer = buffer.lstrip()
                if not buffer:
                    break

                if not inside_array:
                    if buffer[0] != "[":
                        raise ValueError(f"Expected JSON array in {path}")
                    buffer = buffer[1:]
                    inside_array = True
                    continue

                if buffer[0] == "]":
                    return

                if buffer[0] == ",":
                    buffer = buffer[1:]
                    continue

                try:
                    value, index = decoder.raw_decode(buffer)
                except JSONDecodeError:
                    break

                if not isinstance(value, dict):
                    raise ValueError(f"Expected objects inside JSON array: {path}")

                yield value
                buffer = buffer[index:]


def _count_json_array_records(path: Path) -> int:
    return sum(1 for _ in _stream_json_array(path))


def _batched(items: Iterator[Dict[str, Any]], batch_size: int) -> Iterator[List[Dict[str, Any]]]:
    batch: List[Dict[str, Any]] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _load_tokenizer(tokenizer_name: str) -> Any:
    try:
        from transformers import AutoTokenizer  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise ImportError(
            "transformers is required for tokenizer-aware chunking. Install the project dependencies first."
        ) from exc

    try:
        return AutoTokenizer.from_pretrained(tokenizer_name, use_fast=True)
    except Exception as exc:  # pragma: no cover - depends on local cache/network
        raise RuntimeError(f"Failed to load tokenizer '{tokenizer_name}': {exc}") from exc


def _build_token_length_function(tokenizer: Any) -> Callable[[str], int]:
    def length_function(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=True))

    return length_function


def _build_text_splitter(config: ChunkerConfig) -> RecursiveCharacterTextSplitter:
    tokenizer = _load_tokenizer(config.tokenizer_name)
    model_max_length = int(getattr(tokenizer, "model_max_length", config.chunk_size))
    effective_chunk_size = min(config.chunk_size, model_max_length)

    return RecursiveCharacterTextSplitter(
        chunk_size=effective_chunk_size,
        chunk_overlap=config.chunk_overlap,
        length_function=_build_token_length_function(tokenizer),
        separators=["\n\n", "\n", " ", ""],
    )


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _sanitize_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned or "unknown"


CVE_ALIAS_MAP: Dict[str, List[str]] = {
    "CVE-2021-44228": ["Log4Shell", "Apache Log4j RCE"],
    "CVE-2021-45046": ["Log4Shell", "Apache Log4j"],
    "CVE-2017-0144": ["EternalBlue", "MS17-010"],
    "CVE-2020-1472": ["Zerologon", "Netlogon PrivEsc"],
    "CVE-2021-34527": ["PrintNightmare", "Print Spooler RCE"],
    "CVE-2021-36934": ["HiveNightmare", "SeriousSam"],
    "CVE-2014-0160": ["Heartbleed", "OpenSSL Heartbleed"],
    "CVE-2021-34473": ["ProxyShell", "Exchange SSRF"],
    "CVE-2021-34523": ["ProxyShell", "Exchange RCE"],
    "CVE-2021-31207": ["ProxyShell", "Exchange Post-Auth RCE"],
    "CVE-2019-0708": ["BlueKeep", "Windows RDP RCE"],
    "CVE-2022-30190": ["Follina", "MSDT RCE"],
    "CVE-2023-34362": ["MOVEit Transfer SQLi"],
    "CVE-2020-0601": ["CurveBall", "CryptoAPI Spoofing"],
    "CVE-2017-5638": ["Apache Struts Jakarta RCE"],
    "CVE-2021-26084": ["Confluence OGNL RCE"],
    "CVE-2018-13379": ["Fortinet FortiOS SSL-VPN Path Traversal"],
    "CVE-2019-11510": ["Pulse Secure VPN Arbitrary File Read"],
    "CVE-2019-19781": ["Citrix ADC RCE"],
    "CVE-2020-5902": ["F5 BIG-IP TMUI RCE"],
}

ATTACK_TYPE_PATTERNS = [
    ("Remote Code Execution", re.compile(r"\b(remote code execution|rce|execute arbitrary code|arbitrary code execution)\b", re.IGNORECASE)),
    ("SQL Injection", re.compile(r"\b(sql injection|sqli)\b", re.IGNORECASE)),
    ("Privilege Escalation", re.compile(r"\b(privilege escalation|elevation of privilege|gain root|gain admin)\b", re.IGNORECASE)),
    ("Path Traversal", re.compile(r"\b(path traversal|directory traversal|arbitrary file read)\b", re.IGNORECASE)),
    ("Cross-Site Scripting", re.compile(r"\b(cross-site scripting|xss)\b", re.IGNORECASE)),
    ("Buffer Overflow", re.compile(r"\b(buffer overflow|heap overflow|stack overflow|memory corruption|over-read)\b", re.IGNORECASE)),
    ("Server-Side Request Forgery", re.compile(r"\b(server-side request forgery|ssrf)\b", re.IGNORECASE)),
    ("Denial of Service", re.compile(r"\b(denial of service|dos)\b", re.IGNORECASE)),
    ("Authentication Bypass", re.compile(r"\b(authentication bypass|auth bypass|bypass authentication)\b", re.IGNORECASE)),
    ("Information Disclosure", re.compile(r"\b(information disclosure|information leak|sensitive information)\b", re.IGNORECASE)),
]

_CWE_PATTERN = re.compile(r"\bCWE-\d+\b", re.IGNORECASE)


def _format_sequence(values: Sequence[Any]) -> str:
    items = [str(item) for item in values if item not in (None, "")]
    return ", ".join(items) if items else "N/A"


def _load_kev_lookup(path: Path) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return lookup
    for record in _stream_json_array(path):
        cve_id = str(record.get("cve_id", "")).strip()
        if cve_id:
            lookup[cve_id] = record
    return lookup


def _load_epss_lookup(path: Path) -> Dict[str, float]:
    lookup: Dict[str, float] = {}
    if not path.exists():
        return lookup
    try:
        for record in _stream_json_array(path):
            cve_id = str(record.get("cve_id", "")).strip()
            prob = record.get("epss_probability")
            if cve_id and prob is not None:
                try:
                    lookup[cve_id] = float(prob)
                except (TypeError, ValueError):
                    pass
    except Exception as exc:
        LOGGER.warning("Failed to load EPSS lookup: %s", exc)
    return lookup


def _extract_cwe(text: str) -> Optional[str]:
    match = _CWE_PATTERN.search(text)
    return match.group(0).upper() if match else None


def _extract_attack_type(text: str) -> Optional[str]:
    for name, pattern in ATTACK_TYPE_PATTERNS:
        if pattern.search(text):
            return name
    return None


def _extract_vendor_product(
    affected_products: List[Any],
    explicit_vendor: Optional[str] = None,
    explicit_product: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    vendor = explicit_vendor
    product = explicit_product

    if not vendor or not product:
        for p in affected_products:
            p_str = str(p)
            if p_str.startswith("cpe:2.3:"):
                parts = p_str.split(":")
                if len(parts) >= 5:
                    if not vendor and parts[3] != "*":
                        vendor = parts[3]
                    if not product and parts[4] != "*":
                        product = parts[4]
            elif " " in p_str and not vendor and not product:
                parts = p_str.split(" ", 1)
                vendor = parts[0]
                product = parts[1]

    return vendor, product


def _build_nvd_record(
    record: Dict[str, Any],
    kev_lookup: Dict[str, Dict[str, Any]],
    epss_lookup: Optional[Dict[str, float]] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    cve_id = str(record.get("cve_id", "")).strip()
    if not cve_id:
        return None

    kev_record = kev_lookup.get(cve_id)
    epss_score = (epss_lookup or {}).get(cve_id)
    published = record.get("published_date")
    cvss_score = record.get("cvss_score")
    severity = record.get("severity")
    desc = str(record.get("description", "")).strip()
    affected_prods = _safe_list(record.get("affected_products"))

    vendor, product = _extract_vendor_product(affected_prods)
    cwe_id = _extract_cwe(desc)
    attack_type = _extract_attack_type(desc)
    aliases = CVE_ALIAS_MAP.get(cve_id, [])

    metadata: Dict[str, Any] = {
        "source": "nvd",
        "source_record_id": cve_id,
        "cve_id": cve_id,
        "vendor": vendor,
        "product": product,
        "cvss": cvss_score,
        "cvss_score": cvss_score,
        "epss": epss_score,
        "epss_score": epss_score,
        "severity": severity,
        "published": published,
        "publication_date": published,
        "last_modified": record.get("last_modified"),
        "affected_products": affected_prods,
        "kev": bool(kev_record),
        "kev_flag": bool(kev_record),
        "cwe": cwe_id,
        "attack_type": attack_type,
        "aliases": aliases,
        "exploitability": "Ransomware / KEV" if kev_record else ("HIGH" if (cvss_score and float(cvss_score) >= 8.0) else "MEDIUM"),
    }

    if kev_record:
        metadata["kev_date_added"] = kev_record.get("date_added")
        metadata["kev_required_action"] = kev_record.get("required_action")

    # Phase 3 — One vulnerability = One logical document with structured headers
    alias_str = ", ".join(aliases) if aliases else "N/A"
    products_str = _format_sequence(affected_prods)
    text = "\n\n".join(
        [
            f"# [{cve_id}] {product or 'Vulnerability'} Security Overview\nAliases: {alias_str}",
            f"## Description\n{desc}",
            f"## Vulnerability Metrics\n"
            f"- CVE ID: {cve_id}\n"
            f"- CVSS Score: {cvss_score or 'N/A'}\n"
            f"- Severity: {severity or 'UNKNOWN'}\n"
            f"- EPSS Probability: {epss_score if epss_score is not None else 'N/A'}\n"
            f"- In CISA KEV: {bool(kev_record)}\n"
            f"- CWE: {cwe_id or 'N/A'}\n"
            f"- Attack Classification: {attack_type or 'General Security Vulnerability'}",
            f"## Affected Products & Scope\n"
            f"- Vendor: {vendor or 'N/A'}\n"
            f"- Product: {product or 'N/A'}\n"
            f"- Affected Products: {products_str}",
            f"## Dates & Metadata\n"
            f"- Published: {published or 'N/A'}\n"
            f"- Last Modified: {record.get('last_modified', 'N/A')}",
        ]
    )

    return text, metadata


def _build_mitre_record(record: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    technique_id = str(record.get("technique_id", "")).strip()
    if not technique_id:
        return None

    name = record.get("name", "")
    desc = str(record.get("description", "")).strip()
    mitigations = _safe_list(record.get("mitigations"))
    mitigation_names = [
        mitigation.get("name") if isinstance(mitigation, dict) else str(mitigation)
        for mitigation in mitigations
    ]
    tactics = _safe_list(record.get("tactics"))
    platforms = _safe_list(record.get("platforms"))
    attack_type = _extract_attack_type(desc)

    metadata: Dict[str, Any] = {
        "source": "mitre",
        "source_record_id": technique_id,
        "technique_id": technique_id,
        "name": name,
        "cve_id": None,
        "cvss": None,
        "cvss_score": None,
        "published": None,
        "publication_date": None,
        "kev": False,
        "kev_flag": False,
        "epss": None,
        "epss_score": None,
        "tactics": tactics,
        "platforms": platforms,
        "sub_techniques": _safe_list(record.get("sub_techniques")),
        "data_sources": _safe_list(record.get("data_sources")),
        "mitigations": mitigations,
        "attack_type": attack_type or "Adversary Technique",
        "url": record.get("url"),
    }

    text = "\n\n".join(
        [
            f"# [{technique_id}] MITRE ATT&CK Technique: {name}",
            f"## Description\n{desc}",
            f"## Technique Metadata\n"
            f"- Technique ID: {technique_id}\n"
            f"- Name: {name}\n"
            f"- Tactics: {_format_sequence(tactics)}\n"
            f"- Target Platforms: {_format_sequence(platforms)}\n"
            f"- Sub-techniques: {_format_sequence(record.get('sub_techniques', []))}\n"
            f"- Data Sources: {_format_sequence(record.get('data_sources', []))}",
            f"## Mitigations & Defense\n"
            f"- Mitigations: {_format_sequence(mitigation_names)}\n"
            f"- Reference URL: {record.get('url', '')}",
        ]
    )

    return text, metadata


def _build_kev_record(
    record: Dict[str, Any],
    epss_lookup: Optional[Dict[str, float]] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    cve_id = str(record.get("cve_id", "")).strip()
    if not cve_id:
        return None

    epss_score = (epss_lookup or {}).get(cve_id)
    date_added = record.get("date_added")
    vendor = record.get("vendor")
    product = record.get("product")
    vuln_name = record.get("vulnerability_name", "")
    desc = str(record.get("short_description", "")).strip()

    cwe_id = _extract_cwe(desc)
    attack_type = _extract_attack_type(desc)
    aliases = CVE_ALIAS_MAP.get(cve_id, [])

    metadata: Dict[str, Any] = {
        "source": "kev",
        "source_record_id": cve_id,
        "cve_id": cve_id,
        "vendor": vendor,
        "product": product,
        "vulnerability_name": vuln_name,
        "cvss": None,
        "cvss_score": None,
        "epss": epss_score,
        "epss_score": epss_score,
        "published": date_added,
        "publication_date": date_added,
        "kev": True,
        "kev_flag": True,
        "date_added": date_added,
        "required_action": record.get("required_action"),
        "due_date": record.get("due_date"),
        "known_ransomware_campaign_use": record.get("known_ransomware_campaign_use"),
        "cwe": cwe_id,
        "attack_type": attack_type,
        "aliases": aliases,
        "exploitability": "Known Ransomware Campaign Use" if record.get("known_ransomware_campaign_use") == "Known" else "Exploited in Wild",
    }

    alias_str = ", ".join(aliases) if aliases else "N/A"
    text = "\n\n".join(
        [
            f"# [{cve_id}] CISA Known Exploited Vulnerability: {vuln_name or product or cve_id}\nAliases: {alias_str}",
            f"## Description\n{desc}",
            f"## KEV Exploitation Details\n"
            f"- CVE ID: {cve_id}\n"
            f"- Vendor: {vendor or 'N/A'}\n"
            f"- Product: {product or 'N/A'}\n"
            f"- Vulnerability Name: {vuln_name}\n"
            f"- Date Added to KEV: {date_added or 'N/A'}\n"
            f"- EPSS Score: {epss_score if epss_score is not None else 'N/A'}\n"
            f"- Ransomware Campaign Use: {record.get('known_ransomware_campaign_use', 'Unknown')}\n"
            f"- Attack Type: {attack_type or 'Exploited Vulnerability'}",
            f"## Required Remediation & Action\n"
            f"- Required Action: {record.get('required_action', 'Apply vendor patches immediately')}\n"
            f"- Mitigation Due Date: {record.get('due_date', 'N/A')}\n"
            f"- Additional Notes: {record.get('notes', 'N/A')}",
        ]
    )

    return text, metadata


def _build_chunk_rows(
    records: Sequence[Dict[str, Any]],
    source_name: str,
    splitter: RecursiveCharacterTextSplitter,
    kev_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    epss_lookup: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    chunk_rows: List[Dict[str, Any]] = []

    for record_index, record in enumerate(records):
        if source_name == "nvd":
            built = _build_nvd_record(record, kev_lookup or {}, epss_lookup)
        elif source_name == "mitre":
            built = _build_mitre_record(record)
        else:
            built = _build_kev_record(record, epss_lookup)

        if built is None:
            continue

        text, metadata = built
        source_record_id = str(metadata.get("source_record_id", "unknown"))
        chunks = splitter.split_text(text)

        for chunk_index, chunk_text in enumerate(chunks):
            chunk_id = f"{source_name}:{_sanitize_identifier(source_record_id)}:{chunk_index:04d}"
            chunk_metadata = dict(metadata)
            chunk_metadata.update(
                {
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index,
                    "chunk_count": len(chunks),
                    "record_index": record_index,
                }
            )

            chunk_rows.append(
                {
                    "id": chunk_id,
                    "text": chunk_text,
                    "metadata": chunk_metadata,
                }
            )

    return chunk_rows


class _ChunkJsonWriter:
    """Incrementally write a JSON array while preserving valid restart points."""

    def __init__(self, output_file: Path) -> None:
        self.output_file = output_file
        self._handle: Optional[Any] = None
        self._has_items = False

    def initialize(self, checkpoint: ChunkerCheckpoint) -> None:
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        if checkpoint.chunks_written == 0 or not self.output_file.exists():
            with self.output_file.open("wb") as handle:
                handle.write(b"[")
                handle.flush()
                os.fsync(handle.fileno())
            self._has_items = False
            self._handle = self.output_file.open("r+b")
            self._handle.seek(1)
            return

        with self.output_file.open("r+b") as handle:
            handle.truncate(checkpoint.file_position)
            handle.flush()
            os.fsync(handle.fileno())

        self._handle = self.output_file.open("r+b")
        self._handle.seek(checkpoint.file_position)
        self._has_items = checkpoint.chunks_written > 0

    def append_batch(self, rows: Sequence[Dict[str, Any]]) -> int:
        if self._handle is None:
            raise RuntimeError("Chunk writer has not been initialized")

        if not rows:
            return self.position

        batch_bytes = b",".join(
            json.dumps(row, ensure_ascii=False).encode("utf-8") for row in rows
        )

        if self._has_items:
            self._handle.write(b",")

        self._handle.write(batch_bytes)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._has_items = True
        return self.position

    def finalize(self) -> int:
        if self._handle is None:
            raise RuntimeError("Chunk writer has not been initialized")

        self._handle.write(b"]")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        return self.position

    @property
    def position(self) -> int:
        if self._handle is None:
            return 0
        return self._handle.tell()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _load_checkpoint(path: Path) -> Optional[ChunkerCheckpoint]:
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return ChunkerCheckpoint(
        source_name=str(payload.get("source_name", SOURCE_ORDER[0])),
        next_record_index=int(payload.get("next_record_index", 0)),
        chunks_written=int(payload.get("chunks_written", 0)),
        file_position=int(payload.get("file_position", 1)),
        complete=bool(payload.get("complete", False)),
    )


def _save_checkpoint(path: Path, checkpoint: ChunkerCheckpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "source_name": checkpoint.source_name,
                "next_record_index": checkpoint.next_record_index,
                "chunks_written": checkpoint.chunks_written,
                "file_position": checkpoint.file_position,
                "complete": checkpoint.complete,
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )


def _source_paths(processed_dir: Path) -> Dict[str, Path]:
    return {
        "nvd": processed_dir / "nvd.json",
        "mitre": processed_dir / "mitre.json",
        "kev": processed_dir / "kev.json",
        "epss": processed_dir / "epss.json",
    }


def _count_records_by_source(source_paths: Dict[str, Path]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    count_bar = tqdm(total=len(SOURCE_ORDER), desc="Counting sources", unit="source", ncols=100)

    try:
        for source_name in SOURCE_ORDER:
            source_path = source_paths[source_name]
            totals[source_name] = _count_json_array_records(source_path)
            count_bar.update(1)
            count_bar.set_postfix({source_name: totals[source_name]})
            LOGGER.info("Counted %d records in %s", totals[source_name], source_name.upper())
    finally:
        count_bar.close()

    return totals


def _process_source(
    source_name: str,
    source_path: Path,
    splitter: RecursiveCharacterTextSplitter,
    writer: _ChunkJsonWriter,
    checkpoint_path: Path,
    start_record_index: int,
    source_total: int,
    global_processed: int,
    global_total: int,
    chunk_total: int,
    chunk_batch_size: int,
    kev_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    epss_lookup: Optional[Dict[str, float]] = None,
) -> Tuple[ChunkerCheckpoint, int, int]:
    iterator = _stream_json_array(source_path)
    for _ in range(start_record_index):
        next(iterator, None)

    remaining = max(0, source_total - start_record_index)
    record_bar = tqdm(
        total=remaining,
        desc=f"Loading {source_name.upper()}",
        unit="record",
        ncols=100,
    )
    chunk_bar = tqdm(desc="Chunks generated", unit="chunk", ncols=100)

    source_processed = start_record_index
    batch_records: List[Dict[str, Any]] = []
    batch_number = (start_record_index // chunk_batch_size) + 1
    checkpoint = ChunkerCheckpoint(
        source_name=source_name,
        next_record_index=start_record_index,
        chunks_written=chunk_total,
        file_position=writer.position,
        complete=False,
    )

    try:
        for record in iterator:
            batch_records.append(record)
            source_processed += 1
            global_processed += 1
            record_bar.update(1)

            if len(batch_records) < chunk_batch_size:
                continue

            LOGGER.info(
                "Processing %s batch %d | records %d-%d of %d",
                source_name.upper(),
                batch_number,
                source_processed - len(batch_records) + 1,
                source_processed,
                source_total,
            )

            chunk_rows = _build_chunk_rows(batch_records, source_name, splitter, kev_lookup, epss_lookup)
            new_position = writer.append_batch(chunk_rows)
            chunk_total += len(chunk_rows)
            chunk_bar.update(len(chunk_rows))

            checkpoint = ChunkerCheckpoint(
                source_name=source_name,
                next_record_index=source_processed,
                chunks_written=chunk_total,
                file_position=new_position,
                complete=False,
            )
            _save_checkpoint(checkpoint_path, checkpoint)

            LOGGER.info(
                "Processed %d / %d records | Current batch: %d | Chunks generated: %d",
                global_processed,
                global_total,
                batch_number,
                chunk_total,
            )

            batch_records.clear()
            batch_number += 1
            gc.collect()

        if batch_records:
            LOGGER.info(
                "Processing %s final batch %d | records %d-%d of %d",
                source_name.upper(),
                batch_number,
                source_processed - len(batch_records) + 1,
                source_processed,
                source_total,
            )

            chunk_rows = _build_chunk_rows(batch_records, source_name, splitter, kev_lookup, epss_lookup)
            new_position = writer.append_batch(chunk_rows)
            chunk_total += len(chunk_rows)
            chunk_bar.update(len(chunk_rows))

            checkpoint = ChunkerCheckpoint(
                source_name=source_name,
                next_record_index=source_processed,
                chunks_written=chunk_total,
                file_position=new_position,
                complete=False,
            )
            _save_checkpoint(checkpoint_path, checkpoint)

            LOGGER.info(
                "Processed %d / %d records | Current batch: %d | Chunks generated: %d",
                global_processed,
                global_total,
                batch_number,
                chunk_total,
            )

            batch_records.clear()
            gc.collect()

    finally:
        record_bar.close()
        chunk_bar.close()

    return checkpoint, global_processed, chunk_total


def run(config: Optional[ChunkerConfig] = None) -> Path:
    """Run Module 2.1 and persist chunked CTI documents."""
    _configure_logging()
    runtime_config = config or ChunkerConfig()

    source_paths = _source_paths(runtime_config.processed_dir)
    for source_name, source_path in source_paths.items():
        if not source_path.exists():
            raise FileNotFoundError(f"Processed file not found: {source_path}")

    LOGGER.info("Starting CTI chunking pipeline")
    LOGGER.info("Processed directory: %s", runtime_config.processed_dir)
    LOGGER.info("Output file: %s", runtime_config.output_file)
    LOGGER.info("Checkpoint file: %s", runtime_config.checkpoint_file)
    LOGGER.info("Chunk batch size: %d", runtime_config.chunk_batch_size)
    LOGGER.info("Chunk size: %d tokens", runtime_config.chunk_size)
    LOGGER.info("Chunk overlap: %d tokens", runtime_config.chunk_overlap)

    checkpoint = _load_checkpoint(runtime_config.checkpoint_file)
    if checkpoint and checkpoint.complete and runtime_config.output_file.exists():
        LOGGER.info("Chunking already complete; using existing output at %s", runtime_config.output_file)
        return runtime_config.output_file

    if checkpoint is None:
        checkpoint = ChunkerCheckpoint(
            source_name=SOURCE_ORDER[0],
            next_record_index=0,
            chunks_written=0,
            file_position=1,
            complete=False,
        )
        if runtime_config.output_file.exists():
            LOGGER.warning(
                "No checkpoint found; overwriting stale chunk output at %s",
                runtime_config.output_file,
            )
    elif not runtime_config.output_file.exists():
        LOGGER.warning(
            "Checkpoint found but output file is missing; restarting chunking from scratch"
        )
        checkpoint = ChunkerCheckpoint(
            source_name=SOURCE_ORDER[0],
            next_record_index=0,
            chunks_written=0,
            file_position=1,
            complete=False,
        )

    record_totals = _count_records_by_source(source_paths)
    splitter = _build_text_splitter(runtime_config)
    kev_lookup = _load_kev_lookup(source_paths["kev"])
    epss_lookup = _load_epss_lookup(source_paths["epss"])
    writer = _ChunkJsonWriter(runtime_config.output_file)
    writer.initialize(checkpoint)

    global_total = sum(record_totals.values())
    global_processed = sum(
        record_totals[source]
        for source in SOURCE_ORDER
        if SOURCE_ORDER.index(source) < SOURCE_ORDER.index(checkpoint.source_name)
    ) + checkpoint.next_record_index if checkpoint.source_name in SOURCE_ORDER else checkpoint.next_record_index
    total_chunks = checkpoint.chunks_written

    try:
        start_index = SOURCE_ORDER.index(checkpoint.source_name)
    except ValueError:
        start_index = 0

    try:
        for source_name in SOURCE_ORDER[start_index:]:
            source_path = source_paths[source_name]
            start_record_index = checkpoint.next_record_index if source_name == checkpoint.source_name else 0
            if start_record_index >= record_totals[source_name]:
                LOGGER.info("Skipping completed source %s", source_name.upper())
                checkpoint = ChunkerCheckpoint(
                    source_name=source_name,
                    next_record_index=record_totals[source_name],
                    chunks_written=total_chunks,
                    file_position=writer.position,
                    complete=False,
                )
                continue

            LOGGER.info("Starting %s records: %d", source_name.upper(), record_totals[source_name])
            checkpoint, global_processed, total_chunks = _process_source(
                source_name=source_name,
                source_path=source_path,
                splitter=splitter,
                writer=writer,
                checkpoint_path=runtime_config.checkpoint_file,
                start_record_index=start_record_index,
                source_total=record_totals[source_name],
                global_processed=global_processed,
                global_total=global_total,
                chunk_total=total_chunks,
                chunk_batch_size=runtime_config.chunk_batch_size,
                kev_lookup=kev_lookup if source_name == "nvd" else None,
                epss_lookup=epss_lookup,
            )

            if source_name != SOURCE_ORDER[-1]:
                next_source = SOURCE_ORDER[SOURCE_ORDER.index(source_name) + 1]
                checkpoint = ChunkerCheckpoint(
                    source_name=next_source,
                    next_record_index=0,
                    chunks_written=total_chunks,
                    file_position=writer.position,
                    complete=False,
                )
                _save_checkpoint(runtime_config.checkpoint_file, checkpoint)

        final_position = writer.finalize()
        checkpoint = ChunkerCheckpoint(
            source_name=SOURCE_ORDER[-1],
            next_record_index=record_totals[SOURCE_ORDER[-1]],
            chunks_written=total_chunks,
            file_position=final_position,
            complete=True,
        )
        _save_checkpoint(runtime_config.checkpoint_file, checkpoint)

    finally:
        writer.close()

    LOGGER.info("Chunking complete")
    LOGGER.info("Total records processed: %d", global_processed)
    LOGGER.info("Total chunks written: %d", total_chunks)
    return runtime_config.output_file


if __name__ == "__main__":
    run()

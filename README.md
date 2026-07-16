# SecureRAG CTI Ingestion Pipeline

This repository ingests and normalizes threat intelligence from four sources:
NVD CVEs, MITRE ATT&CK, CISA KEV, and EPSS.

## Project Layout

- `modules/ingestion/ingest_nvd.py` - NVD CVE ingestion
- `modules/ingestion/ingest_mitre.py` - MITRE ATT&CK ingestion
- `modules/ingestion/ingest_kev.py` - CISA KEV ingestion
- `modules/ingestion/epss_fetcher.py` - EPSS ingestion
- `modules/ingestion/verify_sources.py` - validation and cross-source checks
- `data/raw/` - raw downloaded source data
- `data/processed/` - normalized JSON output

## Requirements

- Python 3.10 or newer
- pip

## Install Dependencies

Create and activate a virtual environment, then install the package requirements:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If `python` is not available on your PATH, use the Python Launcher:

```bash
py -3 -m venv .venv
.venv\Scripts\activate
py -3 -m pip install -r requirements.txt
```

## How To Ingest Data

Run each ingestion script from the repository root:

```bash
py -3 modules/ingestion/ingest_nvd.py
py -3 modules/ingestion/ingest_mitre.py
py -3 modules/ingestion/ingest_kev.py
py -3 modules/ingestion/epss_fetcher.py
```

Recommended order:

1. NVD
2. MITRE
3. KEV
4. EPSS

You can also import the package and call the helper exposed in `modules/ingestion/__init__.py`.

## Verify The Output

After ingestion finishes, validate the processed JSON files:

```bash
py -3 modules/ingestion/verify_sources.py
```

## Source Behavior

- NVD uses the NVD API 2.0 with pagination and local page caching.
- MITRE downloads the ATT&CK Enterprise STIX 2.1 JSON bundle from GitHub.
- CISA KEV downloads the official KEV JSON feed.
- EPSS uses the bulk gzipped CSV download as the primary source and falls back to the FIRST.org API if the CSV download fails.

## EPSS Notes

EPSS is updated daily, and the bulk CSV is the preferred path for latest data. The API fallback exists only for resilience.

## NVD API Key

The NVD ingester reads `NVD_API_KEY` from the environment.

Example:

```bash
set NVD_API_KEY=your_api_key_here
```

If the key is not set, the script still works but runs more slowly because of stricter rate limiting.

## Outputs

Each script writes two files:

- `data/raw/<source>_raw.json`
- `data/processed/<source>.json`

The NVD ingester also uses temporary page cache files under `data/raw/nvd_pages/` while it is running.

## Package Usage Example

```python
from modules.ingestion import fetch_all_cves, ingest_mitre, ingest_kev, fetch_epss, verify_sources

fetch_all_cves()
ingest_mitre()
ingest_kev()
fetch_epss()
verify_sources()
```

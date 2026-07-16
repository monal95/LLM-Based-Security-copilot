"""SecureRAG CTI ingestion package.

This package exposes the individual ingestion entry points for the
supported CTI sources and provides a convenience helper to run them all.
"""

from .epss_fetcher import fetch_epss
from .ingest_kev import ingest_kev
from .ingest_mitre import ingest_mitre
from .ingest_nvd import fetch_all_cves
from .verify_sources import main as verify_sources


def run_all_ingestions() -> dict:
	"""Run all ingestion jobs in the recommended order.

	Returns a mapping of source name to the ingested records.
	"""
	results = {
		"nvd": fetch_all_cves(),
		"mitre": ingest_mitre(),
		"kev": ingest_kev(),
		"epss": fetch_epss(),
	}
	return results


__all__ = [
	"fetch_all_cves",
	"ingest_mitre",
	"ingest_kev",
	"fetch_epss",
	"verify_sources",
	"run_all_ingestions",
]

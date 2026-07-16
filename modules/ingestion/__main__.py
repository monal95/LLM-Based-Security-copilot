"""Module entry point for `python -m modules.ingestion`."""

import sys

from . import run_all_ingestions, verify_sources


def main() -> int:
	"""Run all ingestion jobs and then verify the generated datasets."""
	run_all_ingestions()
	success = verify_sources()
	return 0 if success else 1


if __name__ == "__main__":
	sys.exit(main())
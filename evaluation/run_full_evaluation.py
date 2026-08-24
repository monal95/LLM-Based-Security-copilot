"""Convenience CLI for running a full SecureRAG evaluation experiment."""

from __future__ import annotations

import argparse
from pathlib import Path

from evaluation.evaluation_engine import DEFAULT_BASELINE_CONFIG, DEFAULT_QUERIES_FILE, build_experiment_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a full retrieval evaluation experiment")
        parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_FILE)
            parser.add_argument("--config", type=Path, default=DEFAULT_BASELINE_CONFIG)
                parser.add_argument("--mode", choices=["dense", "sparse", "hybrid", "full", "all"], default="all")
                    parser.add_argument("--experiment-name", type=str, default="full_evaluation")
                        args = parser.parse_args()
                        
                            summary = build_experiment_report(
                                    queries_file=args.queries,
                                            config_file=args.config,
                                                    mode=args.mode,
                                                            experiment_name=args.experiment_name,
                                                                )
                                                                
                                                                    print(summary.experiment_dir)
                                                                        return 0
                                                                        
                                                                        
                                                                        if __name__ == "__main__":
                                                                            raise SystemExit(main())
                                                                            """
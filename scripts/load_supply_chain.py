#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from orchestrator.supply_chain import load_archive_csvs


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Meridian archive CSVs into supply_chain.db")
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("archive"),
        help="Directory containing Meridian CSV files (default: archive)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/supply_chain.db"),
        help="SQLite output path (default: data/supply_chain.db)",
    )
    args = parser.parse_args()

    counts = load_archive_csvs(args.archive_dir, args.db_path)
    total = sum(counts.values())
    print(f"Wrote {total} rows to {args.db_path.resolve()}")
    for table, n in counts.items():
        print(f"  {table}: {n}")


if __name__ == "__main__":
    main()

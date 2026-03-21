"""
ALDA (ArduPilot Log Diagnosis Assistant)
Copyright (C) 2026 Dijo

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict


def run_analysis(log_file: str) -> Dict[str, Any]:
    """Run full ALDA analysis pipeline and return structured output."""
    if not os.path.exists(log_file):
        raise FileNotFoundError(f"Log file not found: {log_file}")

    from classifier import classify, default_thresholds
    from parser import extract_features, parse_log
    from visualiser import plot_diagnosis

    dfs, flight_time, msg_counts = parse_log(log_file)
    if not dfs:
        raise RuntimeError("Could not parse any supported DataFlash messages from log")

    features = extract_features(dfs)
    results = classify(features, thresholds=default_thresholds())
    out_dir = os.path.dirname(os.path.abspath(log_file)) or "."
    plot_path = plot_diagnosis(
        dfs, features, results, os.path.basename(log_file), flight_time, out_dir
    )

    return {
        "log_file": os.path.abspath(log_file),
        "flight_time_sec": float(flight_time),
        "message_counts": msg_counts,
        "features": features,
        "diagnosis": [
            {"class": cls, "confidence": float(conf), "evidence": evidence}
            for cls, conf, evidence in results
        ],
        "root_cause": results[0][0],
        "root_confidence": float(results[0][1]),
        "plot_path": plot_path,
    }


def print_text_report(payload: Dict[str, Any], verbose: bool = False) -> None:
    """Print human-readable diagnosis summary."""
    from classifier import default_fixes

    fixes = default_fixes()
    diagnosis = payload["diagnosis"]
    root = diagnosis[0]
    flight_time = payload["flight_time_sec"]
    mins = int(flight_time // 60)
    secs = int(flight_time % 60)

    print("=" * 70)
    print("ALDA - ArduPilot Log Diagnosis Assistant")
    print(f"Log: {payload['log_file']}")
    print(f"Flight time: {mins}m {secs}s")
    print("-" * 70)
    print(f"Root cause: {root['class']} ({root['confidence'] * 100:.1f}%)")
    print(f"Evidence: {root['evidence']}")
    print()

    for i, row in enumerate(diagnosis[1:4], 2):
        print(
            f"#{i} {row['class']} ({row['confidence'] * 100:.1f}%): {row['evidence']}"
        )

    print()
    print("Suggested fixes:")
    for idx, fix in enumerate(fixes.get(root["class"], [])[:4], 1):
        print(f"{idx}. {fix}")

    features = payload["features"]
    keys = sorted(features.keys()) if verbose else sorted(features.keys())[:8]
    print()
    print(f"Extracted features ({len(features)} total):")
    for key in keys:
        print(f"- {key}: {features[key]}")

    print()
    print(f"Plot saved: {payload['plot_path']}")
    print("=" * 70)


def build_arg_parser() -> argparse.ArgumentParser:
    """Create command-line parser for ALDA."""
    parser = argparse.ArgumentParser(description="ArduPilot Log Diagnosis Assistant")
    parser.add_argument("log_file", help="Path to DataFlash .bin/.log file")
    parser.add_argument(
        "--show-thresholds",
        action="store_true",
        help="Print active classifier thresholds",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit structured JSON output"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print all extracted features"
    )
    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.show_thresholds and not args.json:
        from classifier import default_thresholds

        print("Active thresholds:")
        for key, value in default_thresholds().items():
            print(f"- {key}: {value}")
        print()

    try:
        payload = run_analysis(args.log_file)
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text_report(payload, verbose=args.verbose)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

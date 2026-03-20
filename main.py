"""
ArduPilot AI-Assisted Log Diagnosis - v0.1
Author: Dijo 
Repo:   github.com/Dijo-404/alda

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3.
https://www.gnu.org/licenses/gpl-3.0.html

Usage:  python main.py <path_to_log.bin>
"""

import sys
import argparse
from log_analyzer import analyze_log
from rules import THRESHOLDS

def main():
    parser = argparse.ArgumentParser(description="ArduPilot Log Diagnostic Analyzer")
    parser.add_argument("log_file", help="Path to the .bin or .log file to analyze")
    parser.add_argument("--show-thresholds", action="store_true", help="Print the current classification thresholds")
    
    args = parser.parse_args()
    
    if args.show_thresholds:
        print("--- Active Configuration Thresholds ---")
        for key, val in THRESHOLDS.items():
            print(f"  {key}: {val}")
        print("---------------------------------------")
        print()

    outpath = analyze_log(args.log_file)
    print(f"Analysis complete. Report saved: {outpath}")

if __name__ == "__main__":
    main()

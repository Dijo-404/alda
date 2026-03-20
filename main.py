import sys
import argparse
from log_val import analyze_log
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

    # Log validation incorporates the rules, parsing, and plotting.
    outpath = analyze_log(args.log_file)
    print(f"Analysis complete. Report saved: {outpath}")

if __name__ == "__main__":
    main()

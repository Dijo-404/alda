# ALDA
ArduPilot Log Diagnosis Assistant

ALDA is an AI-assisted diagnostic tool for ArduPilot `.bin` logs. It automatically extracts key features, analyzes telemetry data for common failure patterns, and provides actionable suggestions to resolve issues.

## Features
- Analyzes vibration, EKF variance, GPS degradation, compass interference, power issues, and motor imbalance.
- Generates visual multi-panel diagnostic plots for insightful tracking.
- Friendly command-line interface with a clean report summary.

## Prerequisites
Ensure you have the required Python packages installed:
```bash
pip install numpy pandas matplotlib pymavlink
```

## Usage
Run the script by providing the path to an ArduPilot `.bin` log:
```bash
python log_val.py <path_to_log.bin>
```

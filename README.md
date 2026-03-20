# alda

ArduPilot Log Diagnosis Assistant

ALDA is an AI-assisted diagnostic tool for ArduPilot `.bin` logs. It automatically extracts key features, analyzes telemetry data for common failure patterns, and provides actionable suggestions to resolve issues.

## Features

- Analyzes vibration, EKF variance, GPS degradation, compass interference, power issues, and motor imbalance.
- Generates visual multi-panel diagnostic plots for insightful tracking.
- Friendly command-line interface with a clean report summary.
- Modular architecture allowing for easy integration into other pipelines.

## Project Structure

```text
alda/
├── main.py          # Command-line entry point
├── log_val.py       # Core parsing, feature extraction, and report generation logic
├── rules.py         # Diagnostic rules, threshold definitions, and classification logic
├── README.md        # Project documentation
└── .gitignore       # Git ignore rules for logs, plot outputs, and python cache
```

## System Flow Diagram

```mermaid
graph TD
    A[main.py: CLI Input] -->|Log File Path| B[log_val.py: analyze_log]
    B --> C[log_val.py: parse_log]
    C -->|Extracts DataFrames| D[log_val.py: extract_features]
    D -->|Dict of Features| E[rules.py: classify]
    E -->|Rules & Thresholds| F[rules.py: Failure Candidates]
    F -->|Prioritized Issues| G[log_val.py: print_report]
    F -->|Plotting Data| H[log_val.py: plot_diagnosis]
    H --> I[Output: Diagnostic Plot .png]
    G --> J[Output: Terminal Summary]
```

## Prerequisites

Ensure you have the required Python packages installed:

```bash
pip install numpy pandas matplotlib pymavlink
```

## Usage

Run the main script by providing the path to an ArduPilot `.bin` log:

```bash
python main.py <path_to_log.bin>
```

You can also view the current classification thresholds by running:

```bash
python main.py <path_to_log.bin> --show-thresholds
```

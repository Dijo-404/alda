import sys
import os
import numpy as np
import pandas as pd
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

try:
    from pymavlink import mavutil
except ImportError:
    logging.error("pymavlink not installed. Run: pip install pymavlink")
    sys.exit(1)

from rules import classify
from plot_output import plot_diagnosis
from report_output import print_report


def parse_log(filepath):
    """Parse ArduPilot .bin log and extract key telemetry streams."""
    mlog = mavutil.mavlink_connection(filepath, robust_parsing=True)

    data = defaultdict(lambda: {"entries": []})
    msg_counts = defaultdict(int)

    wanted = {"VIBE", "EKF4", "EKF1", "ATT", "GPS", "BAT", "RCIN",
              "COMPASS", "ESC", "MODE", "ERR", "EV", "BARO", "IMU"}

    while True:
        try:
            msg = mlog.recv_match(blocking=False)
            if msg is None:
                break
            mtype = msg.get_type()
            if mtype not in wanted:
                continue
            msg_counts[mtype] += 1
            t = getattr(msg, "TimeUS", None) or getattr(msg, "time_boot_ms", 0)
            t_sec = t / 1e6 if t > 1e6 else t / 1e3

            row = {"time": t_sec}
            for field in msg.get_fieldnames():
                if field not in ("TimeUS", "time_boot_ms", "mavpackettype"):
                    try:
                        row[field] = getattr(msg, field)
                    except Exception:
                        pass
            data[mtype]["entries"].append(row)
        except Exception:
            continue

    dfs = {}
    for mtype, d in data.items():
        entries = d.get("entries", [])
        if entries:
            dfs[mtype] = pd.DataFrame(entries).sort_values("time").reset_index(drop=True)

    total_msgs = sum(msg_counts.values())
    flight_time = 0
    for mtype in ["GPS", "ATT", "VIBE", "BAT"]:
        if mtype in dfs and len(dfs[mtype]) > 1:
            ft = dfs[mtype]["time"].iloc[-1] - dfs[mtype]["time"].iloc[0]
            flight_time = max(flight_time, ft)

    return dfs, flight_time, msg_counts


def extract_features(dfs):
    """Extract diagnostic features from parsed telemetry."""
    features = {}

    if "VIBE" in dfs:
        vdf = dfs["VIBE"]
        for ax in ["VibeX", "VibeY", "VibeZ"]:
            if ax in vdf.columns:
                features[f"vibe_{ax.lower()}_max"]  = float(vdf[ax].max())
                features[f"vibe_{ax.lower()}_mean"] = float(vdf[ax].mean())
        if "Clip0" in vdf.columns:
            features["vibe_clip_total"] = int(
                vdf["Clip0"].iloc[-1] - vdf["Clip0"].iloc[0]
                if len(vdf) > 1 else vdf["Clip0"].sum()
            )

    for ekftype in ["EKF4", "EKF1"]:
        if ekftype in dfs:
            edf = dfs[ekftype]
            for col in ["SV", "SP", "SH", "SVT"]:
                if col in edf.columns:
                    features[f"ekf_{col.lower()}_max"] = float(edf[col].max())
            break

    if "GPS" in dfs:
        gdf = dfs["GPS"]
        if "HDop" in gdf.columns:
            features["gps_hdop_max"]  = float(gdf["HDop"].max())
            features["gps_hdop_mean"] = float(gdf["HDop"].mean())
        if "NSats" in gdf.columns:
            features["gps_nsats_min"] = int(gdf["NSats"].min())

    if "BAT" in dfs:
        bdf = dfs["BAT"]
        if "Volt" in bdf.columns:
            features["bat_volt_min"]  = float(bdf["Volt"].min())
            features["bat_volt_mean"] = float(bdf["Volt"].mean())
            if len(bdf) > 5:
                volt_diff = bdf["Volt"].diff() / bdf["time"].diff().replace(0, np.nan)
                features["bat_volt_drop_rate"] = float(volt_diff.min())

    if "COMPASS" in dfs:
        cdf = dfs["COMPASS"]
        for axis_set in [["MagX","MagY","MagZ"], ["Mag2X","Mag2Y","Mag2Z"]]:
            if all(a in cdf.columns for a in axis_set):
                mag_field = np.sqrt(sum(cdf[a]**2 for a in axis_set))
                features["mag_field_range"] = float(mag_field.max() - mag_field.min())
                features["mag_field_mean"]  = float(mag_field.mean())
                break

    if "ATT" in dfs:
        adf = dfs["ATT"]
        if "DesRoll" in adf.columns and "Roll" in adf.columns:
            features["att_roll_err_max"]  = float((adf["DesRoll"] - adf["Roll"]).abs().max())
        if "DesPitch" in adf.columns and "Pitch" in adf.columns:
            features["att_pitch_err_max"] = float((adf["DesPitch"] - adf["Pitch"]).abs().max())

    if "ERR" in dfs:
        edf = dfs["ERR"]
        if "Subsys" in edf.columns:
            features["rc_failsafe_count"] = int((edf["Subsys"] == 3).sum())

    if "ESC" in dfs:
        esdf = dfs["ESC"]
        rpm_cols = [c for c in esdf.columns if "RPM" in c.upper() or c.startswith("Rpm")]
        if len(rpm_cols) >= 2:
            rpm_data = esdf[rpm_cols].dropna()
            if len(rpm_data) > 0:
                spread = rpm_data.max(axis=1) - rpm_data.min(axis=1)
                features["motor_rpm_spread_max"]  = float(spread.max())
                features["motor_rpm_spread_mean"] = float(spread.mean())

    return features


def analyze_log(filepath):
    if not os.path.exists(filepath):
        logging.error(f"File not found: {filepath}")
        sys.exit(1)

    out_dir = os.path.dirname(os.path.abspath(filepath)) or "."

    dfs, flight_time, msg_counts = parse_log(filepath)

    if not dfs:
        logging.error("Could not parse any messages.")
        sys.exit(1)

    features = extract_features(dfs)
    results = classify(features)

    logname = os.path.basename(filepath)
    print_report(results, features, logname, flight_time)

    outpath = plot_diagnosis(dfs, features, results, logname, flight_time, out_dir)
    logging.info(f"Diagnosis plot saved to {outpath}")
    return outpath

def main():
    if len(sys.argv) < 2:
        logging.info("Usage:   python log_analyzer.py <path_to_log.bin>")
        logging.info("Example: python log_analyzer.py crash.bin")
        sys.exit(1)

    filepath = sys.argv[1]
    analyze_log(filepath)

if __name__ == "__main__":
    main()

"""
ArduPilot AI-Assisted Log Diagnosis - Demo v0.1
Author: Dijo (GSoC 2026 Applicant)
Repo:   github.com/Dijo-404

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3.
https://www.gnu.org/licenses/gpl-3.0.html

Usage:  python log_val.py <path_to_log.bin>
"""

import sys
import os
import numpy as np
import pandas as pd
import logging
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend - works without $DISPLAY
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

try:
    from pymavlink import mavutil
except ImportError:
    logging.error("pymavlink not installed. Run: pip install pymavlink")
    sys.exit(1)

from rules import THRESHOLDS, FAILURE_COLORS, FIXES, classify


# -- Data Parsers -------------------------------------------------------------
THRESHOLDS = {
    "vibe_warn":      30.0,   # m/s^2  - VIBE.VibeX/Y/Z warning level
    "vibe_crit":      60.0,   # m/s^2  - VIBE.VibeX/Y/Z critical level
    "hdop_warn":       2.0,   # HDOP > 2.0 = GPS degraded
    "nsats_warn":      6,     # Satellites < 6 = GPS unreliable
    "ekf_var_warn":    1.0,   # EKF4 SV/SP/SH variance gate
    "bat_sag":         0.3,   # V/s   - battery voltage drop rate
    "mag_field_min":  120.0,  # uT    - compass field range min
    "mag_field_max":  550.0,  # uT    - compass field range max
    "att_diverge":    15.0,   # deg   - |DesRoll-Roll| > 15 deg = mechanical
    "heading_dev":    30.0,   # deg   - compass vs GPS heading deviation
}

FAILURE_COLORS = {
    "vibration_high":        "#E74C3C",
    "ekf_failure":           "#9B59B6",
    "compass_interference":  "#F39C12",
    "gps_glitch":            "#3498DB",
    "motor_imbalance":       "#E67E22",
    "power_issue":           "#E91E63",
    "rc_failsafe":           "#1ABC9C",
    "healthy":               "#2ECC71",
    "unknown":               "#95A5A6",
}


# -- Log Parser ---------------------------------------------------------------
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

    # Convert to DataFrames
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


# -- Feature Extractor --------------------------------------------------------
def extract_features(dfs):
    """Extract diagnostic features from parsed telemetry."""
    features = {}

    # -- VIBE features --
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

    # -- EKF features --
    for ekftype in ["EKF4", "EKF1"]:
        if ekftype in dfs:
            edf = dfs[ekftype]
            for col in ["SV", "SP", "SH", "SVT"]:
                if col in edf.columns:
                    features[f"ekf_{col.lower()}_max"] = float(edf[col].max())
            break

    # -- GPS features --
    if "GPS" in dfs:
        gdf = dfs["GPS"]
        if "HDop" in gdf.columns:
            features["gps_hdop_max"]  = float(gdf["HDop"].max())
            features["gps_hdop_mean"] = float(gdf["HDop"].mean())
        if "NSats" in gdf.columns:
            features["gps_nsats_min"] = int(gdf["NSats"].min())

    # -- Battery features --
    if "BAT" in dfs:
        bdf = dfs["BAT"]
        if "Volt" in bdf.columns:
            features["bat_volt_min"]  = float(bdf["Volt"].min())
            features["bat_volt_mean"] = float(bdf["Volt"].mean())
            if len(bdf) > 5:
                volt_diff = bdf["Volt"].diff() / bdf["time"].diff().replace(0, np.nan)
                features["bat_volt_drop_rate"] = float(volt_diff.min())

    # -- Compass features --
    if "COMPASS" in dfs:
        cdf = dfs["COMPASS"]
        for axis_set in [["MagX","MagY","MagZ"], ["Mag2X","Mag2Y","Mag2Z"]]:
            if all(a in cdf.columns for a in axis_set):
                mag_field = np.sqrt(sum(cdf[a]**2 for a in axis_set))
                features["mag_field_range"] = float(mag_field.max() - mag_field.min())
                features["mag_field_mean"]  = float(mag_field.mean())
                break

    # -- ATT divergence --
    if "ATT" in dfs:
        adf = dfs["ATT"]
        if "DesRoll" in adf.columns and "Roll" in adf.columns:
            features["att_roll_err_max"]  = float((adf["DesRoll"] - adf["Roll"]).abs().max())
        if "DesPitch" in adf.columns and "Pitch" in adf.columns:
            features["att_pitch_err_max"] = float((adf["DesPitch"] - adf["Pitch"]).abs().max())

    # -- RC failsafe --
    if "ERR" in dfs:
        edf = dfs["ERR"]
        if "Subsys" in edf.columns:
            features["rc_failsafe_count"] = int((edf["Subsys"] == 3).sum())

    # -- ESC motor spread --
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


# -- Visualisation -------------------------------------------------------------
def plot_diagnosis(dfs, features, results, logname, flight_time, out_dir):
    """Generate and save a multi-panel diagnostic plot."""
    root_cause, confidence, evidence = results[0]
    color = FAILURE_COLORS.get(root_cause, "#95A5A6")

    fig = plt.figure(figsize=(18, 13))
    fig.patch.set_facecolor("#0D1117")
    fig.suptitle(
        f"ArduDiag  -  {logname}\n"
        f"Root Cause: {root_cause.replace('_',' ').upper()}  "
        f"({confidence*100:.0f}% confidence)  |  Flight: "
        f"{int(flight_time//60)}m {int(flight_time%60)}s",
        color=color, fontsize=13, fontweight="bold", y=0.98
    )

    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.50, wspace=0.35)

    plot_specs = [
        ("VIBE",  "VibeX",  "Vibration X (m/s^2)",   "#E74C3C",
         THRESHOLDS["vibe_warn"], THRESHOLDS["vibe_crit"]),
        ("EKF4",  "SV",     "EKF Velocity Variance", "#9B59B6",
         THRESHOLDS["ekf_var_warn"], None),
        ("GPS",   "HDop",   "GPS HDOP",              "#3498DB",
         THRESHOLDS["hdop_warn"], None),
        ("BAT",   "Volt",   "Battery Voltage (V)",   "#E91E63",
         None, None),
        ("ATT",   "Roll",   "Roll vs DesRoll (deg)",   "#2ECC71",
         None, None),
    ]

    for i, (mtype, field, ylabel, lcolor, warn, crit) in enumerate(plot_specs):
        row, col = divmod(i, 2)
        ax = fig.add_subplot(gs[row, col])
        ax.set_facecolor("#161B22")
        ax.tick_params(colors="#8B949E", labelsize=7)
        for spine in ax.spines.values():
            spine.set_color("#30363D")
        ax.set_title(ylabel, color="#C9D1D9", fontsize=8, pad=4)
        ax.set_xlabel("Time (s)", color="#8B949E", fontsize=6)

        if mtype in dfs and field in dfs[mtype].columns:
            df = dfs[mtype]
            t  = df["time"] - df["time"].iloc[0]
            ax.plot(t, df[field], color=lcolor, linewidth=0.9, alpha=0.9)

            # Overlay DesRoll on ATT panel
            if mtype == "ATT" and "DesRoll" in df.columns:
                ax.plot(t, df["DesRoll"], color="#F39C12", linewidth=0.8,
                        alpha=0.7, linestyle="--", label="DesRoll")
                ax.legend(fontsize=6, facecolor="#161B22", labelcolor="#C9D1D9")

            # Threshold lines
            if warn is not None:
                ax.axhline(warn, color="#F39C12", linewidth=0.8,
                           linestyle="--", alpha=0.8, label=f"warn={warn}")
            if crit is not None:
                ax.axhline(crit, color="#E74C3C", linewidth=0.8,
                           linestyle="--", alpha=0.8, label=f"crit={crit}")
            if warn or crit:
                ax.legend(fontsize=5.5, facecolor="#161B22", labelcolor="#8B949E")
        else:
            ax.text(0.5, 0.5, f"{mtype}.{field}\nnot in this log",
                    ha="center", va="center", color="#8B949E",
                    fontsize=8, transform=ax.transAxes)

    # -- Summary panel (bottom full-width) --
    ax_s = fig.add_subplot(gs[2, :])
    ax_s.set_facecolor("#161B22")
    ax_s.axis("off")
    for spine in ax_s.spines.values():
        spine.set_color("#30363D")

    lines = [
        "  DIAGNOSIS SUMMARY",
        f"  Log: {logname}   |   Flight time: {int(flight_time//60)}m {int(flight_time%60)}s",
        "",
    ]
    for rank, (cls, conf, ev) in enumerate(results[:3], 1):
        filled = int(conf * 22)
        bar    = "#" * filled + "-" * (22 - filled)
        tag    = "  <- ROOT CAUSE" if rank == 1 else ""
        lines.append(f"  #{rank}  {cls.replace('_',' '):<24} [{bar}] {conf*100:.0f}%{tag}")
        lines.append(f"       Evidence: {ev}")
        lines.append("")

    lines.append("  SUGGESTED FIXES:")
    for i, fix in enumerate(FIXES.get(root_cause, [])[:4], 1):
        lines.append(f"  {i}. {fix}")

    lines += [
        "",
        "  ------------------------------------------------------",
        "  ArduDiag v0.1  |  GSoC 2026  |  github.com/Dijo-404",
        "  GPL v3  |  Built on pymavlink * scikit-learn * pandas",
    ]

    ax_s.text(0.01, 0.97, "\n".join(lines),
              transform=ax_s.transAxes, fontsize=7.5,
              verticalalignment="top", color="#C9D1D9",
              fontfamily="monospace")

    # Save
    outpath = os.path.join(out_dir, "diagnosis_output.png")
    plt.savefig(outpath, dpi=160, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return outpath


# -- CLI Report ----------------------------------------------------------------
def print_report(results, features, logname, flight_time):
    B = "\033[1m";  R = "\033[0m"
    RED = "\033[91m"; YEL = "\033[93m"
    GRN = "\033[92m"; CYN = "\033[96m"
    GRY = "\033[90m"

    root_cause, confidence, evidence = results[0]
    col = RED if confidence > 0.75 else YEL if confidence > 0.50 else GRY

    w = 64
    logging.info("\n" + "=" * w)
    logging.info(f"  {B}ArduDiag - AI-Assisted Log Diagnosis  v0.1{R}")
    logging.info(f"  {GRY}GSoC 2026  |  Dijo  |  github.com/Dijo-404{R}")
    logging.info("=" * w)
    logging.info(f"  Log:          {logname}")
    logging.info(f"  Flight time:  {int(flight_time//60)}m {int(flight_time%60)}s")
    logging.info("-" * w)

    bar_len = int(confidence * 32)
    bar     = "#" * bar_len + "-" * (32 - bar_len)
    logging.info(f"\n  {B}ROOT CAUSE :{R}  {col}{B}{root_cause.replace('_',' ').upper()}{R}")
    logging.info(f"  Confidence  :  {col}[{bar}] {confidence*100:.0f}%{R}")
    logging.info(f"  Evidence    :  {CYN}{evidence}{R}")

    if len(results) > 1:
        logging.info(f"\n  {GRY}Other candidates:{R}")
        for cls, conf, ev in results[1:3]:
            logging.info(f"  {GRY}  * {cls.replace('_',' '):<24} ({conf*100:.0f}%)  -  {ev[:52]}{R}")

    logging.info(f"\n  {B}{GRN}SUGGESTED FIXES:{R}")
    for i, fix in enumerate(FIXES.get(root_cause, [])[:4], 1):
        logging.info(f"  {GRN}{i}.{R} {fix}")

    logging.info(f"\n  {GRY}Features extracted ({len(features)} total):{R}")
    for k, v in sorted(features.items())[:8]:
        val = f"{v:.4f}" if isinstance(v, float) else str(v)
        logging.info(f"  {GRY}  {k:<36} {val}{R}")

    logging.info("\n" + "=" * w + "\n")


# -- Main ----------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        logging.info("Usage:   python log_val.py <path_to_log.bin>")
        logging.info("Example: python log_val.py crash.bin")
        sys.exit(1)

    filepath = sys.argv[1]
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

if __name__ == "__main__":
    main()

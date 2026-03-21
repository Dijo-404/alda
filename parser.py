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

from collections import defaultdict
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from pymavlink import mavutil
except ImportError as exc:
    raise ImportError(
        "pymavlink is required. Install with: pip install pymavlink"
    ) from exc


DataFrames = Dict[str, pd.DataFrame]


def parse_log(filepath: str) -> Tuple[DataFrames, float, Dict[str, int]]:
    """Parse an ArduPilot DataFlash log and return message dataframes.

    Parameters
    ----------
    filepath:
        Path to a .bin/.log DataFlash file.

    Returns
    -------
    tuple
        (dfs, flight_time_seconds, message_counts)
    """
    mlog = mavutil.mavlink_connection(filepath, robust_parsing=True)
    raw_data: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    msg_counts: Dict[str, int] = defaultdict(int)

    wanted = {
        "VIBE",
        "EKF4",
        "EKF1",
        "ATT",
        "GPS",
        "BAT",
        "RCIN",
        "COMPASS",
        "ESC",
        "RCOU",
        "MODE",
        "ERR",
        "EV",
    }

    while True:
        try:
            msg = mlog.recv_match(blocking=False)
            if msg is None:
                break
            msg_type = msg.get_type()
            if msg_type not in wanted:
                continue

            msg_counts[msg_type] = msg_counts.get(msg_type, 0) + 1
            row = _message_to_row(msg)
            if row is not None:
                raw_data[msg_type].append(row)
        except Exception:
            continue

    dfs: DataFrames = {}
    for msg_type, rows in raw_data.items():
        if not rows:
            continue
        try:
            df = pd.DataFrame(rows)
            if "time" not in df.columns:
                continue
            dfs[msg_type] = df.sort_values("time").reset_index(drop=True)
        except Exception:
            continue

    flight_time = _estimate_flight_time(dfs)
    return dfs, flight_time, dict(msg_counts)


def extract_features(
    dfs: DataFrames, pre_event_window_sec: float = 30.0
) -> Dict[str, Any]:
    """Extract diagnosis features from parsed telemetry.

    Features are extracted from a pre-event window where possible to avoid
    crash-sequence spikes polluting root-cause attribution.
    """
    features: Dict[str, Any] = {}
    windowed = _apply_pre_event_window(dfs, pre_event_window_sec)

    _extract_vibe_features(windowed, features)
    _extract_ekf_features(windowed, features)
    _extract_gps_features(windowed, features)
    _extract_battery_features(windowed, features)
    _extract_compass_features(windowed, features)
    _extract_attitude_features(windowed, features)
    _extract_rc_failsafe_features(windowed, features)
    _extract_esc_features(windowed, features)
    _extract_rcou_features(windowed, features)

    return features


def _message_to_row(msg: Any) -> Optional[Dict[str, Any]]:
    """Convert one pymavlink message object to a dict row."""
    try:
        raw_t = getattr(msg, "TimeUS", None)
        if raw_t is None:
            raw_t = getattr(msg, "time_boot_ms", None)
        if raw_t is None:
            return None

        t_val = float(raw_t)
        t_sec = t_val / 1e6 if t_val > 1e6 else t_val / 1e3
        row: Dict[str, Any] = {"time": t_sec}

        for field in msg.get_fieldnames():
            if field in {"TimeUS", "time_boot_ms", "mavpackettype"}:
                continue
            try:
                row[field] = getattr(msg, field)
            except Exception:
                continue
        return row
    except Exception:
        return None


def _estimate_flight_time(dfs: DataFrames) -> float:
    """Estimate flight duration from the widest available stream."""
    best = 0.0
    for msg_type in ("GPS", "ATT", "VIBE", "BAT", "MODE"):
        try:
            df = dfs.get(msg_type)
            if df is None or len(df) < 2 or "time" not in df.columns:
                continue
            dur = float(df["time"].iloc[-1] - df["time"].iloc[0])
            best = max(best, dur)
        except Exception:
            continue
    return best


def _apply_pre_event_window(dfs: DataFrames, window_sec: float) -> DataFrames:
    """Restrict telemetry to the pre-event window near first ERR/EV marker."""
    cutoff = _first_event_time(dfs)
    if cutoff is None:
        return dict(dfs)

    start = max(0.0, cutoff - window_sec)
    out: DataFrames = {}

    for msg_type, df in dfs.items():
        try:
            if "time" not in df.columns:
                out[msg_type] = df
                continue
            sliced = df[(df["time"] >= start) & (df["time"] <= cutoff)].copy()
            out[msg_type] = sliced if len(sliced) >= 2 else df
        except Exception:
            out[msg_type] = df

    return out


def _first_event_time(dfs: DataFrames) -> Optional[float]:
    """Return first event marker time from ERR/EV streams."""
    for msg_type in ("ERR", "EV"):
        try:
            df = dfs.get(msg_type)
            if df is None or df.empty or "time" not in df.columns:
                continue
            return float(df["time"].iloc[0])
        except Exception:
            continue
    return None


def _extract_vibe_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract vibration and clipping features."""
    try:
        df = dfs.get("VIBE")
        if df is None or df.empty:
            return
        for axis in ("VibeX", "VibeY", "VibeZ"):
            if axis in df.columns:
                key = axis.lower()
                features[f"vibe_{key}_max"] = float(df[axis].max())
                features[f"vibe_{key}_mean"] = float(df[axis].mean())
        if "Clip0" in df.columns:
            if len(df) >= 2:
                features["vibe_clip_total"] = int(
                    df["Clip0"].iloc[-1] - df["Clip0"].iloc[0]
                )
            else:
                features["vibe_clip_total"] = int(df["Clip0"].fillna(0).sum())
    except Exception:
        return


def _extract_ekf_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract EKF variance indicators from EKF4 or EKF1."""
    for ekf_type in ("EKF4", "EKF1"):
        try:
            df = dfs.get(ekf_type)
            if df is None or df.empty:
                continue
            for col in ("SV", "SP", "SH", "SVT"):
                if col in df.columns:
                    features[f"ekf_{col.lower()}_max"] = float(df[col].max())
            return
        except Exception:
            continue


def _extract_gps_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract GPS quality indicators."""
    try:
        df = dfs.get("GPS")
        if df is None or df.empty:
            return
        if "HDop" in df.columns:
            features["gps_hdop_max"] = float(df["HDop"].max())
            features["gps_hdop_mean"] = float(df["HDop"].mean())
        elif "HDOP" in df.columns:
            features["gps_hdop_max"] = float(df["HDOP"].max())
            features["gps_hdop_mean"] = float(df["HDOP"].mean())
        if "NSats" in df.columns:
            features["gps_nsats_min"] = int(df["NSats"].min())
        elif "Sats" in df.columns:
            features["gps_nsats_min"] = int(df["Sats"].min())
    except Exception:
        return


def _extract_battery_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract battery sag and minimum voltage features."""
    try:
        df = dfs.get("BAT")
        if df is None or df.empty:
            return
        volt_col = _first_present(df.columns, ("Volt", "VoltR", "Voltage"))
        if volt_col is None:
            return

        volt = pd.to_numeric(df[volt_col], errors="coerce")
        time_s = (
            pd.to_numeric(df["time"], errors="coerce") if "time" in df.columns else None
        )
        if volt.isna().all():
            return

        features["bat_volt_min"] = float(volt.min())
        features["bat_volt_mean"] = float(volt.mean())

        if time_s is not None and len(df) >= 5:
            dv = volt.diff()
            dt = time_s.diff().replace(0, np.nan)
            drop_rate = dv / dt
            if not drop_rate.isna().all():
                features["bat_volt_drop_rate"] = float(drop_rate.min())
    except Exception:
        return


def _extract_compass_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract magnetic field range with graceful missing-data handling."""
    features["compass_data_present"] = False
    try:
        df = dfs.get("COMPASS")
        if df is None or df.empty:
            return
        axis_sets: Iterable[Tuple[str, str, str]] = (
            ("MagX", "MagY", "MagZ"),
            ("Mag2X", "Mag2Y", "Mag2Z"),
        )
        for a1, a2, a3 in axis_sets:
            if {a1, a2, a3}.issubset(set(df.columns)):
                mag = np.sqrt(
                    pd.to_numeric(df[a1], errors="coerce") ** 2
                    + pd.to_numeric(df[a2], errors="coerce") ** 2
                    + pd.to_numeric(df[a3], errors="coerce") ** 2
                )
                mag = mag.dropna()
                if mag.empty:
                    return
                features["compass_data_present"] = True
                features["mag_field_range"] = float(mag.max() - mag.min())
                features["mag_field_mean"] = float(mag.mean())
                features["mag_field_samples"] = int(len(mag))
                return
    except Exception:
        return


def _extract_attitude_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract attitude tracking error features."""
    try:
        df = dfs.get("ATT")
        if df is None or df.empty:
            return
        if {"DesRoll", "Roll"}.issubset(df.columns):
            err = (
                pd.to_numeric(df["DesRoll"], errors="coerce")
                - pd.to_numeric(df["Roll"], errors="coerce")
            ).abs()
            features["att_roll_err_max"] = float(err.max())
        if {"DesPitch", "Pitch"}.issubset(df.columns):
            err = (
                pd.to_numeric(df["DesPitch"], errors="coerce")
                - pd.to_numeric(df["Pitch"], errors="coerce")
            ).abs()
            features["att_pitch_err_max"] = float(err.max())
    except Exception:
        return


def _extract_rc_failsafe_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract RC failsafe evidence from ERR and MODE/RCIN patterns."""
    features["rc_failsafe_count"] = 0
    features["mode_change_count"] = 0
    features["mode_rtl_land_switches"] = 0
    features["mode_rtl_land_without_input_count"] = 0
    features["mode_rtl_land_with_input_count"] = 0

    try:
        err_df = dfs.get("ERR")
        if err_df is not None and not err_df.empty and "Subsys" in err_df.columns:
            subsys = pd.to_numeric(err_df["Subsys"], errors="coerce")
            features["rc_failsafe_count"] = int((subsys == 3).sum())
    except Exception:
        pass

    try:
        mode_df = dfs.get("MODE")
        if mode_df is None or mode_df.empty:
            return

        mode_col = _first_present(mode_df.columns, ("Mode", "ModeNum", "mode"))
        if mode_col is None or "time" not in mode_df.columns:
            return

        clean = mode_df[["time", mode_col]].copy()
        clean[mode_col] = pd.to_numeric(clean[mode_col], errors="coerce")
        clean = clean.dropna(subset=[mode_col])
        if clean.empty:
            return

        mode_series = clean[mode_col].astype(int)
        transitions = mode_series != mode_series.shift(1)
        changed = clean.loc[transitions].copy()
        changed["prev_mode"] = mode_series.shift(1).loc[transitions]

        features["mode_change_count"] = int(len(changed))

        targets = changed[changed[mode_col].isin([9, 11])]
        features["mode_rtl_land_switches"] = int(len(targets))

        rcin_df = dfs.get("RCIN")
        for _, row in targets.iterrows():
            switch_t = float(row["time"])
            pilot_input = _pilot_input_detected(rcin_df, switch_t)
            if pilot_input:
                features["mode_rtl_land_with_input_count"] += 1
            else:
                features["mode_rtl_land_without_input_count"] += 1
    except Exception:
        return


def _pilot_input_detected(rcin_df: Optional[pd.DataFrame], switch_time: float) -> bool:
    """Heuristic: detect meaningful stick input before an auto-mode switch."""
    if rcin_df is None or rcin_df.empty or "time" not in rcin_df.columns:
        return False

    try:
        channels = [c for c in rcin_df.columns if c.upper().startswith(("C", "CHAN"))]
        if not channels:
            return False

        window = rcin_df[
            (rcin_df["time"] >= switch_time - 2.0) & (rcin_df["time"] <= switch_time)
        ]
        if len(window) < 3:
            return False

        for ch in channels[:8]:
            series = pd.to_numeric(window[ch], errors="coerce").dropna()
            if len(series) < 3:
                continue
            if float(series.diff().abs().max()) >= 120.0:
                return True
    except Exception:
        return False
    return False


def _extract_esc_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract ESC RPM spread features."""
    try:
        df = dfs.get("ESC")
        if df is None or df.empty:
            return
        rpm_cols = [c for c in df.columns if "RPM" in c.upper() or c.startswith("Rpm")]
        if len(rpm_cols) < 2:
            return
        rpm = df[rpm_cols].apply(pd.to_numeric, errors="coerce").dropna(how="all")
        if rpm.empty:
            return
        spread = rpm.max(axis=1) - rpm.min(axis=1)
        features["motor_rpm_spread_max"] = float(spread.max())
        features["motor_rpm_spread_mean"] = float(spread.mean())
    except Exception:
        return


def _extract_rcou_features(dfs: DataFrames, features: Dict[str, Any]) -> None:
    """Extract output saturation features from RCOU."""
    try:
        df = dfs.get("RCOU")
        if df is None or df.empty:
            return
        pwm_cols = [c for c in df.columns if c.startswith("C") and c != "Ch"]
        if not pwm_cols:
            return
        pwm = df[pwm_cols].apply(pd.to_numeric, errors="coerce").dropna(how="all")
        if pwm.empty:
            return
        max_pwm = pwm.max(axis=1)
        features["motor_max_pwm"] = float(max_pwm.max())
        features["motor_saturation_pct"] = float(
            (max_pwm > 1900.0).sum() / len(max_pwm)
        )
    except Exception:
        return


def _first_present(columns: Iterable[str], names: Iterable[str]) -> Optional[str]:
    """Return first present column name from a candidate list."""
    col_set = set(columns)
    for name in names:
        if name in col_set:
            return name
    return None

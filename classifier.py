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

from typing import Any, Dict, List, Tuple


def default_thresholds() -> Dict[str, float]:
    """Return classifier thresholds."""
    return {
        "vibe_warn": 30.0,
        "vibe_crit": 60.0,
        "hdop_warn": 2.0,
        "nsats_warn": 6.0,
        "ekf_var_warn": 1.0,
        "bat_sag": 0.3,
        "att_diverge": 15.0,
        "compass_range_warn": 260.0,
        "compass_range_crit": 500.0,
    }


def default_fixes() -> Dict[str, List[str]]:
    """Return remediation guidance for each failure class."""
    return {
        "vibration_high": [
            "Add vibration damping foam/gel mounts between FC and frame",
            "Re-balance propellers and check motor bearings",
            "Enable notch filtering (INS_HNTCH_ENABLE=1)",
            "Tighten frame and stack hardware",
        ],
        "ekf_failure": [
            "Recalibrate accelerometers on level ground",
            "Validate EKF health before arming",
            "Check GPS quality and magnetic environment",
            "Inspect EK3/EKF related parameters",
        ],
        "compass_interference": [
            "Move compass away from power wiring and ESCs",
            "Re-run compass calibration in open area",
            "Enable motor interference compensation",
            "Use external compass mast if available",
        ],
        "gps_glitch": [
            "Ensure clear sky view and adequate satellite lock",
            "Enable additional GNSS constellations",
            "Inspect GPS antenna and placement",
            "Review GPS/EKF quality gates",
        ],
        "motor_imbalance": [
            "Verify motor directions and ESC calibration",
            "Inspect props for damage and imbalance",
            "Check mechanical alignment of motors/arms",
            "Review thrust linearization and mixer mapping",
        ],
        "power_issue": [
            "Check battery health and C-rating under load",
            "Inspect connectors, solder joints, and cable resistance",
            "Calibrate battery monitor parameters",
            "Review low-voltage failsafe configuration",
        ],
        "rc_failsafe": [
            "Check transmitter battery and RF link quality",
            "Validate FS_THR_ENABLE / RC failsafe params",
            "Review antenna orientation and placement",
            "Verify RTL/LAND failsafe behavior in bench tests",
        ],
        "thrust_loss": [
            "Check thrust-to-weight ratio and payload",
            "Inspect motors/props for degraded output",
            "Validate ESC limits and output consistency",
            "Review hover throttle and saturation behavior",
        ],
        "unknown": [
            "Collect additional logs with full logging enabled",
            "Correlate pilot notes/video with event timeline",
            "Post log to discuss.ardupilot.org for peer review",
            "Re-run analysis with additional telemetry streams",
        ],
    }


def classify(
    features: Dict[str, Any],
    thresholds: Dict[str, float] | None = None,
    min_confidence: float = 0.45,
) -> List[Tuple[str, float, str]]:
    """Classify likely failure classes from extracted features."""
    t = thresholds or default_thresholds()
    candidates: List[Tuple[str, float, str]] = []

    vibe_max = max(
        float(features.get("vibe_vibex_max", 0.0)),
        float(features.get("vibe_vibey_max", 0.0)),
        float(features.get("vibe_vibez_max", 0.0)),
    )
    vibe_clip = int(features.get("vibe_clip_total", 0))
    if vibe_max >= t["vibe_crit"]:
        conf = min(0.94, 0.70 + (vibe_max - t["vibe_crit"]) / 120.0)
        if vibe_clip > 0:
            conf = min(0.96, conf + 0.03)
        candidates.append(
            (
                "vibration_high",
                conf,
                f"VIBE max={vibe_max:.1f} m/s^2 (critical>={t['vibe_crit']:.0f}), clip={vibe_clip}",
            )
        )
    elif vibe_max >= t["vibe_warn"]:
        conf = (
            0.42
            + (vibe_max - t["vibe_warn"]) / (t["vibe_crit"] - t["vibe_warn"]) * 0.26
        )
        if vibe_clip > 0:
            conf += 0.04
        candidates.append(
            (
                "vibration_high",
                min(0.78, conf),
                f"VIBE max={vibe_max:.1f} m/s^2 (warn>={t['vibe_warn']:.0f}), clip={vibe_clip}",
            )
        )

    ekf_max = max(
        float(features.get("ekf_sv_max", 0.0)),
        float(features.get("ekf_sp_max", 0.0)),
        float(features.get("ekf_sh_max", 0.0)),
    )
    if ekf_max >= t["ekf_var_warn"]:
        conf = min(0.88, 0.55 + (ekf_max - t["ekf_var_warn"]) / 6.0)
        candidates.append(
            (
                "ekf_failure",
                conf,
                f"EKF variance max={ekf_max:.3f} (gate>={t['ekf_var_warn']:.2f})",
            )
        )

    hdop = float(features.get("gps_hdop_max", 0.0))
    nsats = float(features.get("gps_nsats_min", 99.0))
    if hdop >= t["hdop_warn"] or nsats < t["nsats_warn"]:
        conf = 0.52
        if hdop >= t["hdop_warn"]:
            conf += min(0.24, (hdop - t["hdop_warn"]) / 4.0)
        if nsats < t["nsats_warn"]:
            conf += 0.10
        candidates.append(
            (
                "gps_glitch",
                min(0.86, conf),
                f"GPS HDOP max={hdop:.2f}, NSats min={int(nsats)}",
            )
        )

    mag_range = float(features.get("mag_field_range", 0.0))
    mag_samples = int(features.get("mag_field_samples", 0))
    compass_present = bool(features.get("compass_data_present", False))
    if compass_present and mag_samples >= 20 and mag_range >= t["compass_range_warn"]:
        conf = 0.48 + min(0.36, (mag_range - t["compass_range_warn"]) / 600.0)
        note = ""
        if vibe_max >= t["vibe_crit"]:
            conf -= 0.12
            note = " (reduced due high vibration near crash)"
        if float(features.get("bat_volt_drop_rate", 0.0)) <= -3.0:
            conf -= 0.08
            if not note:
                note = " (reduced due severe power collapse)"
        conf = max(0.20, min(0.86, conf))
        candidates.append(
            (
                "compass_interference",
                conf,
                f"Mag field range={mag_range:.1f} uT over {mag_samples} samples{note}",
            )
        )

    bat_drop = float(features.get("bat_volt_drop_rate", 0.0))
    bat_min = float(features.get("bat_volt_min", 99.0))
    if bat_drop <= -t["bat_sag"] or bat_min < 3.3:
        conf = 0.58
        if bat_drop <= -t["bat_sag"]:
            conf += min(0.30, abs(bat_drop) / 10.0)
        if bat_min < 3.3:
            conf += 0.08
        candidates.append(
            (
                "power_issue",
                min(0.93, conf),
                f"Voltage drop rate={bat_drop:.3f} V/s, minimum cell/pack proxy={bat_min:.2f}V",
            )
        )

    rpm_spread = float(features.get("motor_rpm_spread_max", 0.0))
    roll_err = float(features.get("att_roll_err_max", 0.0))
    pitch_err = float(features.get("att_pitch_err_max", 0.0))
    if (
        rpm_spread > 500.0
        or roll_err > t["att_diverge"]
        or pitch_err > t["att_diverge"]
    ):
        conf = 0.48
        evid = []
        if rpm_spread > 500.0:
            conf += min(0.24, rpm_spread / 3500.0)
            evid.append(f"RPM spread={rpm_spread:.0f}")
        if roll_err > t["att_diverge"]:
            conf += 0.08
            evid.append(f"roll err={roll_err:.1f}")
        if pitch_err > t["att_diverge"]:
            conf += 0.08
            evid.append(f"pitch err={pitch_err:.1f}")
        candidates.append(("motor_imbalance", min(0.88, conf), " | ".join(evid)))

    sat_pct = float(features.get("motor_saturation_pct", 0.0))
    max_pwm = float(features.get("motor_max_pwm", 0.0))
    if sat_pct > 0.30:
        conf = min(0.88, 0.56 + sat_pct * 0.45)
        candidates.append(
            (
                "thrust_loss",
                conf,
                f"Motors saturated (>1900us) for {sat_pct * 100:.0f}% of samples, max PWM={max_pwm:.0f}",
            )
        )

    rc_fs = int(features.get("rc_failsafe_count", 0))
    mode_without_input = int(
        features.get(
            "mode_rtl_land_without_input_count",
            features.get("auto_mode_switch_count", 0),
        )
    )
    mode_with_input = int(features.get("mode_rtl_land_with_input_count", 0))
    mode_total = int(features.get("mode_rtl_land_switches", 0))

    if rc_fs > 0 or mode_without_input > 0:
        conf = 0.58
        evid_parts: List[str] = []
        if rc_fs > 0:
            conf += min(0.22, rc_fs * 0.05)
            evid_parts.append(f"ERR.Subsys=3 count={rc_fs}")
        if mode_without_input > 0:
            conf += min(0.25, 0.15 + mode_without_input * 0.04)
            evid_parts.append(
                f"Auto RTL/LAND switch {mode_without_input}x without pilot input"
            )
        if mode_with_input > 0:
            evid_parts.append(f"{mode_with_input} RTL/LAND switch(es) with pilot input")
        if mode_total > 0:
            evid_parts.append(f"total RTL/LAND switches={mode_total}")
        candidates.append(("rc_failsafe", min(0.95, conf), " | ".join(evid_parts)))

    if not candidates:
        return [
            (
                "unknown",
                0.0,
                "No threshold violations detected; data may represent healthy flight or missing telemetry.",
            )
        ]

    candidates.sort(key=lambda x: x[1], reverse=True)
    candidates = _apply_causal_arbiter(candidates, features, t)

    retained: List[Tuple[str, float, str]] = []
    suppressed: List[Tuple[str, float, str]] = []
    for row in candidates:
        if row[1] >= min_confidence:
            retained.append(row)
        else:
            suppressed.append(row)

    if not retained:
        if suppressed:
            detail = ", ".join([f"{c}={s:.2f}" for c, s, _ in suppressed])
            return [
                (
                    "unknown",
                    0.0,
                    f"All candidates below confidence floor {min_confidence:.2f}; demoted: {detail}",
                )
            ]
        return [("unknown", 0.0, "No reliable candidates produced.")]

    if suppressed:
        detail = ", ".join([f"{c}={s:.2f}" for c, s, _ in suppressed])
        retained.append(
            ("unknown", 0.0, f"Low-confidence candidates demoted to unknown: {detail}")
        )

    return retained


def _apply_causal_arbiter(
    candidates: List[Tuple[str, float, str]],
    features: Dict[str, Any],
    thresholds: Dict[str, float],
) -> List[Tuple[str, float, str]]:
    """Apply post-ranking causal ordering and annotations."""
    classes = [c[0] for c in candidates]

    if "vibration_high" in classes and "ekf_failure" in classes:
        vi = classes.index("vibration_high")
        ei = classes.index("ekf_failure")
        if vi > ei:
            candidates[vi], candidates[ei] = candidates[ei], candidates[vi]
        candidates = [
            (
                cls,
                conf,
                ev + (" [downstream of vibration]" if cls == "ekf_failure" else ""),
            )
            for cls, conf, ev in candidates
        ]

    classes = [c[0] for c in candidates]
    if "power_issue" in classes and "vibration_high" in classes:
        bat_drop = float(features.get("bat_volt_drop_rate", 0.0))
        if bat_drop <= -2.0:
            pi = classes.index("power_issue")
            vi = classes.index("vibration_high")
            if pi > vi:
                candidates[pi], candidates[vi] = candidates[vi], candidates[pi]
            candidates = [
                (
                    cls,
                    conf,
                    ev
                    + (
                        " [downstream of power loss]" if cls == "vibration_high" else ""
                    ),
                )
                for cls, conf, ev in candidates
            ]

    classes = [c[0] for c in candidates]
    if "power_issue" in classes and "thrust_loss" in classes:
        pi = classes.index("power_issue")
        ti = classes.index("thrust_loss")
        if pi > ti and float(features.get("bat_volt_drop_rate", 0.0)) <= -1.5:
            candidates[pi], candidates[ti] = candidates[ti], candidates[pi]

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates

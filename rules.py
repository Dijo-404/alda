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
    "thrust_loss":           "#D35400",
    "power_issue":           "#E91E63",
    "rc_failsafe":           "#1ABC9C",
    "healthy":               "#2ECC71",
    "unknown":               "#95A5A6",
}

FIXES = {
    "vibration_high": [
        "Add vibration damping foam/gel mounts between FC and frame",
        "Re-balance all propellers - even small imbalance causes resonance",
        "Check motor bearings for wear - replace if rough",
        "Tighten all frame screws - loose parts amplify vibration",
        "Enable FFT notch filter (INS_HNTCH_ENABLE=1) to cancel resonance",
    ],
    "ekf_failure": [
        "Recalibrate accelerometers on a level surface",
        "Ensure HDop < 1.5 and NSats > 8 before arming",
        "Review EKF_CHECK_THRESH (default 0.8 - lower = stricter)",
        "Separate GPS from ESCs and battery leads",
        "Check EK3_MAG_CAL for compass input to EKF",
    ],
    "compass_interference": [
        "Move compass away from power cables and ESCs",
        "Re-run Live Calibration (COMPASS_CAL=1) in open area",
        "Enable motor interference compensation (COMPASS_MOTCT=2)",
        "Mount external compass on GPS mast away from frame",
        "Check COMPASS_DEC for local magnetic declination",
    ],
    "gps_glitch": [
        "Ensure clear sky view - avoid buildings and trees",
        "Move GPS away from carbon fibre frame (blocks signal)",
        "Enable multiple constellations (GPS_GNSS_MODE)",
        "Increase GPS_HDOP_GOOD if operating in low-signal areas",
        "Check EK3_GPS_CHECK bitmask for pre-arm GPS quality",
    ],
    "motor_imbalance": [
        "Verify motor rotation directions are correct",
        "Run ESC calibration (throttle sweep)",
        "Inspect propellers for chips or asymmetry",
        "Check MOT_THST_EXPO for thrust linearisation",
        "Swap ESC signal cables - incorrect mapping = asymmetric thrust",
    ],
    "power_issue": [
        "Upgrade battery C-rating if voltage sags under load",
        "Measure voltage at FC vs battery to check cable resistance",
        "Review BATT_LOW_VOLT and BATT_CRT_VOLT failsafe thresholds",
        "Enable battery monitor (BATT_MONITOR=4)",
        "Calibrate power module (BATT_AMP_PERVLT, BATT_VOLT_MULT)",
    ],
    "thrust_loss": [
        "Check motor/propeller sizing - craft may be underpowered for its weight",
        "Review MOT_THST_HOVER - if > 0.6 the craft is near thrust limit",
        "Reduce payload weight or upgrade to higher KV motors",
        "Check for a failed motor - one motor at max forces others to compensate",
        "Review RCOU in logs - if all motors hit 1900+ simultaneously = underpowered",
    ],
    "rc_failsafe": [
        "Check transmitter battery level",
        "Verify FS_THR_ENABLE=1 and FS_THR_VALUE below min throttle",
        "Orient transmitter antenna vertically during flight",
        "Review RC_FS_MODE=1 (RTL) for safe failsafe behaviour",
        "Increase transmitter power if legally permitted",
    ],
    "unknown": [
        "Post log on discuss.ardupilot.org with flight description",
        "Run Mission Planner Auto Analysis for quick automated check",
        "Enable full logging: LOG_BITMASK=65535 for next flight",
    ],
}

def classify(features):
    """
    Rule-based classifier using official ArduPilot threshold values.
    Causal arbiter resolves vibration-vs-EKF ordering.
    Returns list of (failure_class, confidence, evidence) sorted by confidence.
    """
    T = THRESHOLDS
    candidates = []

    vibe_max = max(
        features.get("vibe_vibex_max", 0),
        features.get("vibe_vibey_max", 0),
        features.get("vibe_vibez_max", 0),
    )
    clip = features.get("vibe_clip_total", 0)
    if vibe_max >= T["vibe_crit"]:
        conf = min(0.97, 0.75 + (vibe_max - T["vibe_crit"]) / 100)
        candidates.append(("vibration_high", conf,
            f"VIBE max = {vibe_max:.1f} m/s^2 (critical >= {T['vibe_crit']}) | Clips: {clip}"))
    elif vibe_max >= T["vibe_warn"]:
        conf = 0.50 + (vibe_max - T["vibe_warn"]) / (T["vibe_crit"] - T["vibe_warn"]) * 0.25
        if clip > 0:
            conf = min(0.85, conf + 0.10)
        candidates.append(("vibration_high", conf,
            f"VIBE max = {vibe_max:.1f} m/s^2 (warning >= {T['vibe_warn']}) | Clips: {clip}"))

    ekf_max = max(
        features.get("ekf_sv_max", 0),
        features.get("ekf_sp_max", 0),
        features.get("ekf_sh_max", 0),
    )
    if ekf_max >= T["ekf_var_warn"]:
        conf = min(0.92, 0.65 + (ekf_max - T["ekf_var_warn"]) / 5)
        candidates.append(("ekf_failure", conf,
            f"EKF variance max = {ekf_max:.3f} (gate >= {T['ekf_var_warn']})"))

    hdop  = features.get("gps_hdop_max", 0)
    nsats = features.get("gps_nsats_min", 99)
    if hdop >= T["hdop_warn"] or nsats < T["nsats_warn"]:
        conf = 0.60
        if hdop  >= T["hdop_warn"]:  conf += min(0.25, (hdop - T["hdop_warn"]) / 4)
        if nsats  < T["nsats_warn"]: conf += 0.10
        candidates.append(("gps_glitch", min(0.90, conf),
            f"GPS HDop max = {hdop:.2f} (warn >= {T['hdop_warn']}) | NSats min = {nsats}"))

    mag_range = features.get("mag_field_range", 0)
    if mag_range > 200:
        conf = min(0.93, 0.60 + mag_range / 1000)
        candidates.append(("compass_interference", conf,
            f"Mag field range = {mag_range:.1f} uT (high variation = interference)"))

    bat_drop = features.get("bat_volt_drop_rate", 0)
    bat_min  = features.get("bat_volt_min", 99)
    if bat_drop < -T["bat_sag"] or bat_min < 3.3:
        conf = 0.70 if bat_drop < -T["bat_sag"] else 0.60
        candidates.append(("power_issue", conf,
            f"Bat drop rate = {bat_drop:.3f} V/s | min volt = {bat_min:.2f}V"))

    rpm_spread = features.get("motor_rpm_spread_max", 0)
    att_roll   = features.get("att_roll_err_max",  0)
    att_pitch  = features.get("att_pitch_err_max", 0)
    if rpm_spread > 500 or att_roll > T["att_diverge"] or att_pitch > T["att_diverge"]:
        conf  = 0.55
        parts = []
        if rpm_spread > 500:
            conf += min(0.30, rpm_spread / 3000)
            parts.append(f"RPM spread = {rpm_spread:.0f}")
        if att_roll > T["att_diverge"]:
            conf += 0.10
            parts.append(f"Roll err = {att_roll:.1f} deg")
        if att_pitch > T["att_diverge"]:
            conf += 0.10
            parts.append(f"Pitch err = {att_pitch:.1f} deg")
        candidates.append(("motor_imbalance", min(0.92, conf),
            "  |  ".join(parts) or "ATT divergence detected"))

    sat_pct  = features.get("motor_saturation_pct", 0)
    max_pwm  = features.get("motor_max_pwm", 0)
    if sat_pct > 0.3:
        conf = min(0.92, 0.65 + sat_pct * 0.4)
        candidates.append(("thrust_loss", conf,
            f"Motors saturated >1900us PWM for {sat_pct*100:.0f}% of flight"
            f" | max PWM = {max_pwm:.0f}us"))

    rc_fs = features.get("rc_failsafe_count", 0)
    if rc_fs > 0:
        candidates.append(("rc_failsafe", min(0.95, 0.80 + rc_fs * 0.05),
            f"RC failsafe triggered {rc_fs}x (ERR.Subsys=3)"))

    if not candidates:
        return [("unknown", 0.0,
            "No threshold violations detected - log may be healthy or incomplete")]

    candidates.sort(key=lambda x: x[1], reverse=True)

    classes = [c[0] for c in candidates]
    if "vibration_high" in classes and "ekf_failure" in classes:
        vi = classes.index("vibration_high")
        ei = classes.index("ekf_failure")
        if vi > ei:
            candidates[vi], candidates[ei] = candidates[ei], candidates[vi]
        updated = []
        for cls, conf, ev in candidates:
            if cls == "ekf_failure":
                ev += "  [downstream of vibration]"
            updated.append((cls, conf, ev))
        candidates = updated

    return candidates
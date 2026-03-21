from rules import classify


def test_unknown_when_no_signals():
    results = classify({})
    root, confidence, evidence = results[0]

    assert root == "unknown"
    assert confidence == 0.0
    assert "No threshold violations" in evidence


def test_vibration_critical_detected():
    features = {
        "vibe_vibex_max": 61.0,
        "vibe_vibey_max": 22.0,
        "vibe_vibez_max": 19.0,
        "vibe_clip_total": 4,
    }

    results = classify(features)
    root, confidence, evidence = results[0]

    assert root == "vibration_high"
    assert confidence >= 0.75
    assert "critical" in evidence


def test_ekf_marked_downstream_when_vibration_present():
    features = {
        "vibe_vibex_max": 62.0,
        "vibe_vibey_max": 10.0,
        "vibe_vibez_max": 5.0,
        "ekf_sv_max": 2.2,
        "ekf_sp_max": 1.1,
        "ekf_sh_max": 0.8,
    }

    results = classify(features)

    assert results[0][0] == "vibration_high"
    ekf_rows = [r for r in results if r[0] == "ekf_failure"]
    assert ekf_rows, "Expected ekf_failure candidate when EKF variance exceeds threshold"
    assert "[downstream of vibration]" in ekf_rows[0][2]


def test_gps_glitch_triggered_by_bad_hdop_or_low_satellites():
    features = {
        "gps_hdop_max": 2.4,
        "gps_nsats_min": 5,
    }

    results = classify(features)
    classes = [row[0] for row in results]

    assert "gps_glitch" in classes


def test_rc_failsafe_confidence_increases_with_count():
    one_event = classify({"rc_failsafe_count": 1})
    five_events = classify({"rc_failsafe_count": 5})

    one = [r for r in one_event if r[0] == "rc_failsafe"][0][1]
    five = [r for r in five_events if r[0] == "rc_failsafe"][0][1]

    assert five >= one
    assert five <= 0.95

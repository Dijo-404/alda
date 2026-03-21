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

from classifier import classify as _classify
from classifier import default_fixes, default_thresholds


THRESHOLDS = default_thresholds()
FIXES = default_fixes()
FAILURE_COLORS = {
    "vibration_high": "#E74C3C",
    "ekf_failure": "#9B59B6",
    "compass_interference": "#F39C12",
    "gps_glitch": "#3498DB",
    "motor_imbalance": "#E67E22",
    "thrust_loss": "#D35400",
    "power_issue": "#E91E63",
    "rc_failsafe": "#1ABC9C",
    "unknown": "#95A5A6",
}


def classify(features: Dict[str, Any]) -> List[Tuple[str, float, str]]:
    """Backward-compatible classify function for tests and legacy imports."""
    return _classify(features, thresholds=THRESHOLDS)

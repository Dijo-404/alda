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

from typing import Any, Dict

from main import run_analysis


def analyze_log(filepath: str) -> str:
    """Backward-compatible wrapper returning the generated plot path."""
    payload: Dict[str, Any] = run_analysis(filepath)
    return str(payload["plot_path"])

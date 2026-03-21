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

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import pandas as pd


FAILURE_COLORS: Dict[str, str] = {
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


def plot_diagnosis(
    dfs: Dict[str, pd.DataFrame],
    features: Dict[str, Any],
    results: List[Tuple[str, float, str]],
    logname: str,
    flight_time: float,
    out_dir: str,
) -> str:
    """Render and save a diagnosis panel plot.

    The function never raises on missing or short dataframes.
    """
    del features
    root_cause, confidence, _ = results[0]
    color = FAILURE_COLORS.get(root_cause, "#95A5A6")

    fig = plt.figure(figsize=(16, 12))
    fig.patch.set_facecolor("#0D1117")
    fig.suptitle(
        "ALDA Diagnosis\n"
        f"Root Cause: {root_cause.upper()} ({confidence * 100:.0f}%) | "
        f"Flight: {int(flight_time // 60)}m {int(flight_time % 60)}s",
        color=color,
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )

    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.45, wspace=0.28)
    specs = _plot_specs()

    for idx, spec in enumerate(specs):
        row, col = divmod(idx, 2)
        ax = fig.add_subplot(gs[row, col])
        _style_axis(ax)
        ax.set_title(spec["title"], color="#C9D1D9", fontsize=9)
        ax.set_xlabel("Time (s)", color="#8B949E", fontsize=8)
        _plot_panel(ax, dfs, spec)

    ax_summary = fig.add_subplot(gs[3, :])
    _style_axis(ax_summary)
    ax_summary.axis("off")
    _plot_summary(ax_summary, results)

    os.makedirs(out_dir, exist_ok=True)
    outpath = os.path.join(out_dir, "diagnosis_output.png")
    plt.savefig(outpath, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return outpath


def _plot_specs() -> List[Dict[str, Any]]:
    """Return panel plotting definitions."""
    return [
        {
            "msg_candidates": ["VIBE"],
            "field_candidates": ["VibeX", "VibeY", "VibeZ"],
            "title": "Vibration",
            "color": "#E74C3C",
            "overlay": None,
        },
        {
            "msg_candidates": ["EKF4", "EKF1"],
            "field_candidates": ["SV", "SP", "SH", "SVT"],
            "title": "EKF Variance",
            "color": "#9B59B6",
            "overlay": None,
        },
        {
            "msg_candidates": ["GPS"],
            "field_candidates": ["HDop", "HDOP"],
            "title": "GPS HDOP",
            "color": "#3498DB",
            "overlay": None,
        },
        {
            "msg_candidates": ["BAT"],
            "field_candidates": ["Volt", "VoltR", "Voltage"],
            "title": "Battery Voltage",
            "color": "#E91E63",
            "overlay": None,
        },
        {
            "msg_candidates": ["ATT"],
            "field_candidates": ["Roll"],
            "title": "Roll vs Desired Roll",
            "color": "#2ECC71",
            "overlay": "DesRoll",
        },
        {
            "msg_candidates": ["GPS"],
            "field_candidates": ["NSats", "Sats"],
            "title": "GPS Satellites",
            "color": "#1ABC9C",
            "overlay": None,
        },
    ]


def _plot_panel(ax: Any, dfs: Dict[str, pd.DataFrame], spec: Dict[str, Any]) -> None:
    """Plot one telemetry panel safely."""
    msg_type, field, df = _resolve_series(
        dfs,
        spec["msg_candidates"],
        spec["field_candidates"],
    )
    if df is None or field is None:
        _panel_note(ax, "Telemetry unavailable")
        return

    try:
        if "time" not in df.columns or len(df) < 2:
            _panel_note(ax, "Not enough rows to plot")
            return
        y = pd.to_numeric(df[field], errors="coerce")
        x = pd.to_numeric(df["time"], errors="coerce")
        if y.dropna().shape[0] < 2:
            _panel_note(ax, "Not enough numeric samples")
            return

        x_norm = x - x.iloc[0]
        ax.plot(
            x_norm,
            y,
            color=spec["color"],
            linewidth=1.0,
            alpha=0.92,
            label=f"{msg_type}.{field}",
        )

        overlay = spec.get("overlay")
        if overlay and overlay in df.columns:
            over = pd.to_numeric(df[overlay], errors="coerce")
            if over.dropna().shape[0] >= 2:
                ax.plot(
                    x_norm,
                    over,
                    color="#F39C12",
                    linewidth=0.9,
                    alpha=0.8,
                    linestyle="--",
                    label=f"{msg_type}.{overlay}",
                )

        ax.legend(fontsize=7, facecolor="#161B22", labelcolor="#C9D1D9", loc="best")
    except Exception:
        _panel_note(ax, "Plot rendering error")


def _plot_summary(ax: Any, results: List[Tuple[str, float, str]]) -> None:
    """Plot summary table-like text with top candidates."""
    lines = ["Diagnosis Summary", ""]
    top = results[:4]
    for i, (cls, conf, ev) in enumerate(top, 1):
        lines.append(f"#{i} {cls:<22} {conf * 100:>5.1f}%")
        lines.append(f"    Evidence: {ev}")
    ax.text(
        0.01,
        0.97,
        "\n".join(lines),
        transform=ax.transAxes,
        fontsize=8,
        verticalalignment="top",
        color="#C9D1D9",
        fontfamily="monospace",
    )


def _resolve_series(
    dfs: Dict[str, pd.DataFrame],
    msg_candidates: Iterable[str],
    field_candidates: Iterable[str],
) -> Tuple[Optional[str], Optional[str], Optional[pd.DataFrame]]:
    """Find first matching (message, field, dataframe) tuple."""
    for msg_type in msg_candidates:
        try:
            df = dfs.get(msg_type)
            if df is None or df.empty:
                continue
            for field in field_candidates:
                if field in df.columns:
                    return msg_type, field, df
        except Exception:
            continue
    return None, None, None


def _style_axis(ax: Any) -> None:
    """Apply dark theme axis styling."""
    ax.set_facecolor("#161B22")
    ax.tick_params(colors="#8B949E", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#30363D")


def _panel_note(ax: Any, note: str) -> None:
    """Render a centered note inside a panel."""
    ax.text(
        0.5,
        0.5,
        note,
        ha="center",
        va="center",
        color="#8B949E",
        fontsize=8,
        transform=ax.transAxes,
    )

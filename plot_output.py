import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

from rules import THRESHOLDS, FAILURE_COLORS, FIXES


def _resolve_series(dfs, msg_candidates, field_candidates):
    """Find first available message/field pair and return (msg_type, field, dataframe)."""
    for msg_type in msg_candidates:
        df = dfs.get(msg_type)
        if df is None:
            continue
        for field in field_candidates:
            if field in df.columns:
                return msg_type, field, df
    return None, None, None


def _style_axis(ax):
    ax.set_facecolor("#161B22")
    ax.tick_params(colors="#8B949E", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#30363D")


def plot_diagnosis(dfs, features, results, logname, flight_time, out_dir):
    """Generate and save a multi-panel diagnostic plot."""
    del features  # Reserved for future panel annotations.

    root_cause, confidence, evidence = results[0]
    color = FAILURE_COLORS.get(root_cause, "#95A5A6")

    fig = plt.figure(figsize=(18, 14))
    fig.patch.set_facecolor("#0D1117")
    fig.suptitle(
        f"ArduDiag  -  {logname}\n"
        f"Root Cause: {root_cause.replace('_',' ').upper()}  "
        f"({confidence*100:.0f}% confidence)  |  Flight: "
        f"{int(flight_time//60)}m {int(flight_time%60)}s",
        color=color,
        fontsize=14,
        fontweight="bold",
        y=0.985,
    )

    gs = gridspec.GridSpec(
        4,
        2,
        figure=fig,
        hspace=0.45,
        wspace=0.28,
        height_ratios=[1, 1, 1, 0.9],
    )

    plot_specs = [
        {
            "msg_candidates": ["VIBE"],
            "field_candidates": ["VibeX", "VibeY", "VibeZ"],
            "title": "Vibration (m/s^2)",
            "color": "#E74C3C",
            "warn": THRESHOLDS["vibe_warn"],
            "crit": THRESHOLDS["vibe_crit"],
            "overlay": None,
        },
        {
            "msg_candidates": ["EKF4", "EKF1"],
            "field_candidates": ["SV", "SP", "SH", "SVT"],
            "title": "EKF Variance",
            "color": "#9B59B6",
            "warn": THRESHOLDS["ekf_var_warn"],
            "crit": None,
            "overlay": None,
        },
        {
            "msg_candidates": ["GPS"],
            "field_candidates": ["HDop", "HDOP"],
            "title": "GPS HDOP",
            "color": "#3498DB",
            "warn": THRESHOLDS["hdop_warn"],
            "crit": None,
            "overlay": None,
        },
        {
            "msg_candidates": ["BAT", "BAT2"],
            "field_candidates": ["Volt", "VoltR", "Voltage"],
            "title": "Battery Voltage (V)",
            "color": "#E91E63",
            "warn": None,
            "crit": None,
            "overlay": None,
        },
        {
            "msg_candidates": ["ATT"],
            "field_candidates": ["Roll"],
            "title": "Roll vs Desired Roll (deg)",
            "color": "#2ECC71",
            "warn": None,
            "crit": None,
            "overlay": "DesRoll",
        },
        {
            "msg_candidates": ["GPS"],
            "field_candidates": ["NSats", "Sats"],
            "title": "GPS Satellites",
            "color": "#1ABC9C",
            "warn": None,
            "crit": THRESHOLDS["nsats_warn"],
            "overlay": None,
        },
    ]

    for i, spec in enumerate(plot_specs):
        row, col = divmod(i, 2)
        ax = fig.add_subplot(gs[row, col])
        _style_axis(ax)
        ax.set_title(spec["title"], color="#C9D1D9", fontsize=9, pad=5)
        ax.set_xlabel("Time (s)", color="#8B949E", fontsize=7)

        msg_type, field, df = _resolve_series(
            dfs,
            spec["msg_candidates"],
            spec["field_candidates"],
        )

        if df is not None:
            t = df["time"] - df["time"].iloc[0]
            ax.plot(
                t,
                df[field],
                color=spec["color"],
                linewidth=1.0,
                alpha=0.9,
                label=f"{msg_type}.{field}",
            )

            overlay = spec["overlay"]
            if overlay and overlay in df.columns:
                ax.plot(
                    t,
                    df[overlay],
                    color="#F39C12",
                    linewidth=0.9,
                    alpha=0.75,
                    linestyle="--",
                    label=f"{msg_type}.{overlay}",
                )

            warn = spec["warn"]
            crit = spec["crit"]
            if warn is not None:
                ax.axhline(
                    warn,
                    color="#F39C12",
                    linewidth=0.9,
                    linestyle="--",
                    alpha=0.85,
                    label=f"warn={warn}",
                )
            if crit is not None:
                ax.axhline(
                    crit,
                    color="#E74C3C",
                    linewidth=0.9,
                    linestyle="--",
                    alpha=0.85,
                    label=f"crit={crit}",
                )

            ax.legend(fontsize=6.5, facecolor="#161B22", labelcolor="#C9D1D9", loc="best")
        else:
            ax.text(
                0.5,
                0.5,
                "No matching telemetry\nfor this panel",
                ha="center",
                va="center",
                color="#8B949E",
                fontsize=8,
                transform=ax.transAxes,
            )

    ax_s = fig.add_subplot(gs[3, :])
    _style_axis(ax_s)
    ax_s.axis("off")

    lines = [
        "  DIAGNOSIS SUMMARY",
        f"  Log: {logname}   |   Flight time: {int(flight_time//60)}m {int(flight_time%60)}s",
        "",
    ]
    for rank, (cls, conf, ev) in enumerate(results[:3], 1):
        filled = int(conf * 22)
        bar = "#" * filled + "-" * (22 - filled)
        tag = "  <- ROOT CAUSE" if rank == 1 else ""
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

    ax_s.text(
        0.01,
        0.97,
        "\n".join(lines),
        transform=ax_s.transAxes,
        fontsize=8,
        verticalalignment="top",
        color="#C9D1D9",
        fontfamily="monospace",
    )

    outpath = os.path.join(out_dir, "diagnosis_output.png")
    plt.savefig(outpath, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return outpath

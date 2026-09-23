# -*- coding: utf-8 -*-
"""Bland–Altman plots and bias/LoA tables for timing errors."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import result_paths  # noqa: E402
from stats_io import manuscript_figures_dir, stats_long_dir, stats_models_dir  # noqa: E402
from stats_timing_error import process_subject as build_timing  # noqa: E402

# Stable order / colors for kg×bpm conditions (legend + scatter).
_COND_ORDER = (
    "7kg_10bpm",
    "7kg_16bpm",
    "10kg_10bpm",
    "10kg_16bpm",
    "15kg_10bpm",
    "15kg_16bpm",
)
_COND_COLORS = {
    "7kg_10bpm": "#1f77b4",
    "7kg_16bpm": "#aec7e8",
    "10kg_10bpm": "#2ca02c",
    "10kg_16bpm": "#98df8a",
    "15kg_10bpm": "#d62728",
    "15kg_16bpm": "#ff9896",
}
# 16bpm: darker edge (same-mass 10bpm fill) so light fills stay readable.
_COND_EDGE_COLORS = {
    "7kg_16bpm": "#1f77b4",
    "10kg_16bpm": "#2ca02c",
    "15kg_16bpm": "#d62728",
}

# Combined plot: method = hue; condition = shade within hue (+ hollow 16bpm).
# RiCTO = blue, BoxMarker = red
_METHOD_LINE = {"BoxMarker": "#d62728", "RiCTO": "#1f77b4"}
_COMBINED_FACE = {
    "BoxMarker": {
        "7kg_10bpm": "#a50f15",
        "7kg_16bpm": "#fc9272",
        "10kg_10bpm": "#de2d26",
        "10kg_16bpm": "#fcbba1",
        "15kg_10bpm": "#fb6a4a",
        "15kg_16bpm": "#fee0d2",
    },
    "RiCTO": {
        "7kg_10bpm": "#08519c",
        "7kg_16bpm": "#6baed6",
        "10kg_10bpm": "#2171b5",
        "10kg_16bpm": "#9ecae1",
        "15kg_10bpm": "#4292c6",
        "15kg_16bpm": "#c6dbef",
    },
}
_COMBINED_EDGE = {
    "BoxMarker": {
        "7kg_16bpm": "#a50f15",
        "10kg_16bpm": "#de2d26",
        "15kg_16bpm": "#fb6a4a",
    },
    "RiCTO": {
        "7kg_16bpm": "#08519c",
        "10kg_16bpm": "#2171b5",
        "15kg_16bpm": "#4292c6",
    },
}


def _condition_sort_key(cond: str) -> tuple:
    """Sort by mass then tempo; unknown labels last alphabetical."""
    m = re.match(r"^(\d+)kg_(\d+)bpm", str(cond))
    if m:
        return (int(m.group(1)), int(m.group(2)), str(cond))
    return (10_000, 10_000, str(cond))


def _ordered_conditions(conds: Sequence[str]) -> list[str]:
    uniq = {str(c) for c in conds if c is not None and str(c) != "nan"}
    preferred = [c for c in _COND_ORDER if c in uniq]
    rest = sorted(uniq - set(preferred), key=_condition_sort_key)
    return preferred + rest


def _color_for_condition(cond: str, fallback_idx: int) -> str:
    if cond in _COND_COLORS:
        return _COND_COLORS[cond]
    # Distinct fallback for unexpected condition labels
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap("tab10")
    rgba = cmap(fallback_idx % 10)
    return "#{:02x}{:02x}{:02x}".format(
        int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255)
    )


def bland_altman_stats(diff: np.ndarray) -> dict:
    d = np.asarray(diff, dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return {
            "n": 0,
            "bias": float("nan"),
            "sd": float("nan"),
            "loa_low": float("nan"),
            "loa_high": float("nan"),
        }
    bias = float(np.mean(d))
    sd = float(np.std(d, ddof=1)) if d.size > 1 else 0.0
    return {
        "n": int(d.size),
        "bias": bias,
        "sd": sd,
        "loa_low": bias - 1.96 * sd,
        "loa_high": bias + 1.96 * sd,
    }


def _style_for_condition(cond: str, fallback_idx: int) -> tuple[str, str, float]:
    """Return (facecolor, edgecolor, linewidth) for a condition marker."""
    color = _color_for_condition(cond, fallback_idx)
    edge = _COND_EDGE_COLORS.get(cond)
    if edge is None and "16bpm" in cond:
        edge = color
    is_16bpm = edge is not None
    face = "none" if is_16bpm else color
    edgecolor = edge if is_16bpm else color
    lw = 1.4 if is_16bpm else 0.0
    return face, edgecolor, lw


def _style_for_combined(
    method: str, cond: str, fallback_idx: int
) -> tuple[str, str, float]:
    """Method-colored style for combined BA (BoxMarker=blue, RiCTO=orange)."""
    faces = _COMBINED_FACE.get(method, {})
    edges = _COMBINED_EDGE.get(method, {})
    color = faces.get(cond) or _METHOD_LINE.get(method) or _color_for_condition(
        cond, fallback_idx
    )
    edge = edges.get(cond)
    if edge is None and "16bpm" in cond:
        edge = color
    is_16bpm = "16bpm" in cond
    face = "none" if is_16bpm else color
    edgecolor = edge if is_16bpm else color
    lw = 1.4 if is_16bpm else 0.0
    return face, edgecolor, lw


def _legend_handle(
    cond: str,
    fallback_idx: int,
    *,
    marker: str,
    method: Optional[str] = None,
) -> "Line2D":
    from matplotlib.lines import Line2D

    if method is None:
        face, edge, lw = _style_for_condition(cond, fallback_idx)
    else:
        face, edge, lw = _style_for_combined(method, cond, fallback_idx)
    return Line2D(
        [0],
        [0],
        marker=marker,
        color="none",
        markerfacecolor=face,
        markeredgecolor=edge,
        markeredgewidth=lw if lw > 0 else 0.0,
        markersize=7,
        label=cond,
        linestyle="none",
    )


def _apply_ba_axes(
    ax,
    *,
    diff: np.ndarray,
    stats: dict,
    title: str,
    xlabel: str,
    ylabel: str,
    top_extra_frac: float = 0.65,
    top_extra_min: float = 0.16,
) -> None:
    ax.axhline(0.0, color="black", ls=":", lw=1.0, zorder=1)
    ax.axhline(stats["bias"], color="black", lw=1.5, zorder=2)
    ax.axhline(stats["loa_low"], color="red", ls="--", lw=1.2, zorder=2)
    ax.axhline(stats["loa_high"], color="red", ls="--", lw=1.2, zorder=2)
    ax.set_xlabel(xlabel, fontname="Arial", fontsize=14)
    ax.set_ylabel(ylabel, fontname="Arial", fontsize=14)
    ax.set_title(title, fontname="Arial", fontsize=14)

    y_pts = np.concatenate(
        [
            diff[np.isfinite(diff)],
            np.array(
                [stats["bias"], stats["loa_low"], stats["loa_high"], 0.0],
                dtype=float,
            ),
        ]
    )
    ymin = float(np.min(y_pts))
    ymax = float(np.max(y_pts))
    span = ymax - ymin if ymax > ymin else 0.1
    pad = 0.06 * span
    top_extra = max(top_extra_frac * span, top_extra_min)
    ax.set_ylim(ymin - pad, ymax + pad + top_extra)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(direction="in")


def plot_bland_altman(
    mean_vals: np.ndarray,
    diff: np.ndarray,
    *,
    title: str,
    out_path: Path,
    conditions: Optional[Sequence[str]] = None,
    xlabel: str = "Mean of methods (s)",
    ylabel: str = "Difference (s)",
    dpi: int = 300,
) -> Optional[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    stats = bland_altman_stats(diff)
    if stats["n"] == 0:
        return None
    mean_vals = np.asarray(mean_vals, dtype=float)
    diff = np.asarray(diff, dtype=float)
    fig, ax = plt.subplots(figsize=(8, 6), dpi=dpi)

    if conditions is None:
        ax.scatter(mean_vals, diff, c="0.3", s=28, alpha=0.75, edgecolors="none")
        handles: list = []
    else:
        cond_arr = np.asarray([str(c) for c in conditions], dtype=object)
        if cond_arr.shape[0] != mean_vals.shape[0]:
            raise ValueError(
                f"conditions length {cond_arr.shape[0]} != n points {mean_vals.shape[0]}"
            )
        order = _ordered_conditions(cond_arr.tolist())
        handles = []
        for i, cond in enumerate(order):
            mask = cond_arr == cond
            if not np.any(mask):
                continue
            face, edge, lw = _style_for_condition(cond, i)
            ax.scatter(
                mean_vals[mask],
                diff[mask],
                marker="o",
                facecolors=face,
                edgecolors=edge if lw > 0 else "none",
                s=36,
                alpha=0.9,
                linewidths=lw,
                label=cond,
                zorder=3,
            )
            handles.append(_legend_handle(cond, i, marker="o"))

    _apply_ba_axes(
        ax, diff=diff, stats=stats, title=title, xlabel=xlabel, ylabel=ylabel
    )

    bias_handles = [
        Line2D([0], [0], color="black", lw=1.5, label=f"bias={stats['bias']:.3f}"),
        Line2D(
            [0],
            [0],
            color="red",
            ls="--",
            lw=1.2,
            label="95% limits of agreement",
        ),
    ]
    if handles:
        n_cond = len(handles)
        ncol_cond = max(1, (n_cond + 1) // 2)
        leg_cond = ax.legend(
            handles=handles,
            ncol=ncol_cond,
            frameon=False,
            prop={"family": "Arial", "size": 10},
            loc="upper left",
            columnspacing=0.9,
            handletextpad=0.35,
        )
        ax.add_artist(leg_cond)
        ax.legend(
            handles=bias_handles,
            frameon=False,
            prop={"family": "Arial", "size": 11},
            loc="upper right",
        )
    else:
        ax.legend(handles=bias_handles, frameon=False, prop={"family": "Arial", "size": 11})

    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def plot_bland_altman_combined(
    *,
    mean_box: np.ndarray,
    diff_box: np.ndarray,
    cond_box: Sequence[str],
    mean_ricto: np.ndarray,
    diff_ricto: np.ndarray,
    cond_ricto: Sequence[str],
    title: str,
    out_path: Path,
    xlabel: str = "Mean of methods (s)",
    ylabel: str = "Difference (s)",
    dpi: int = 300,
) -> Optional[Path]:
    """BoxMarker (red ○) + RiCTO (blue △) vs GT; per-method bias/LoA."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    mean_box = np.asarray(mean_box, dtype=float)
    diff_box = np.asarray(diff_box, dtype=float)
    mean_ricto = np.asarray(mean_ricto, dtype=float)
    diff_ricto = np.asarray(diff_ricto, dtype=float)
    cond_box_arr = np.asarray([str(c) for c in cond_box], dtype=object)
    cond_ricto_arr = np.asarray([str(c) for c in cond_ricto], dtype=object)

    st_bm = bland_altman_stats(diff_box)
    st_rc = bland_altman_stats(diff_ricto)
    if st_bm["n"] == 0 and st_rc["n"] == 0:
        return None

    order = _ordered_conditions(
        list(cond_box_arr.tolist()) + list(cond_ricto_arr.tolist())
    )
    fig, ax = plt.subplots(figsize=(8, 6), dpi=dpi)

    bm_handles: list = []
    rc_handles: list = []
    for i, cond in enumerate(order):
        m_bm = cond_box_arr == cond
        if np.any(m_bm):
            face, edge, lw = _style_for_combined("BoxMarker", cond, i)
            ax.scatter(
                mean_box[m_bm],
                diff_box[m_bm],
                marker="o",
                facecolors=face,
                edgecolors=edge if lw > 0 else "none",
                s=36,
                alpha=0.9,
                linewidths=lw,
                zorder=3,
            )
            bm_handles.append(
                _legend_handle(cond, i, marker="o", method="BoxMarker")
            )
        m_rc = cond_ricto_arr == cond
        if np.any(m_rc):
            face, edge, lw = _style_for_combined("RiCTO", cond, i)
            ax.scatter(
                mean_ricto[m_rc],
                diff_ricto[m_rc],
                marker="^",
                facecolors=face,
                edgecolors=edge if lw > 0 else "none",
                s=42,
                alpha=0.9,
                linewidths=lw,
                zorder=3,
            )
            rc_handles.append(_legend_handle(cond, i, marker="^", method="RiCTO"))

    # Zero + per-method bias / 95% limits of agreement
    ax.axhline(0.0, color="black", ls=":", lw=1.0, zorder=1)
    c_bm = _METHOD_LINE["BoxMarker"]
    c_rc = _METHOD_LINE["RiCTO"]
    if st_bm["n"] > 0:
        ax.axhline(st_bm["bias"], color=c_bm, lw=1.5, zorder=2)
        ax.axhline(st_bm["loa_low"], color=c_bm, ls="--", lw=1.2, zorder=2)
        ax.axhline(st_bm["loa_high"], color=c_bm, ls="--", lw=1.2, zorder=2)
    if st_rc["n"] > 0:
        ax.axhline(st_rc["bias"], color=c_rc, lw=1.5, zorder=2)
        ax.axhline(st_rc["loa_low"], color=c_rc, ls="--", lw=1.2, zorder=2)
        ax.axhline(st_rc["loa_high"], color=c_rc, ls="--", lw=1.2, zorder=2)

    ax.set_xlabel(xlabel, fontname="Arial", fontsize=14)
    ax.set_ylabel(ylabel, fontname="Arial", fontsize=14)
    # Title above legends (figure-level) to avoid overlap
    fig.suptitle(title, fontname="Arial", fontsize=14, y=0.995)

    y_parts = [0.0]
    for d, st in ((diff_box, st_bm), (diff_ricto, st_rc)):
        finite = d[np.isfinite(d)]
        if finite.size:
            y_parts.append(finite)
        if st["n"] > 0:
            y_parts.extend([st["bias"], st["loa_low"], st["loa_high"]])
    y_pts = np.concatenate(
        [np.atleast_1d(np.asarray(p, dtype=float)) for p in y_parts]
    )
    ymin = float(np.min(y_pts))
    ymax = float(np.max(y_pts))
    span = ymax - ymin if ymax > ymin else 0.1
    pad = 0.08 * span
    # Legends sit in figure margin above axes — keep only light data padding
    ax.set_ylim(ymin - pad, ymax + pad)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(direction="in")

    bias_handles: list = []
    if st_bm["n"] > 0:
        bias_handles.extend(
            [
                Line2D(
                    [0],
                    [0],
                    color=c_bm,
                    lw=1.5,
                    label=f"bias (BoxMarker)={st_bm['bias']:.3f}",
                ),
                Line2D(
                    [0],
                    [0],
                    color=c_bm,
                    ls="--",
                    lw=1.2,
                    label="95% limits (BoxMarker)",
                ),
            ]
        )
    if st_rc["n"] > 0:
        bias_handles.extend(
            [
                Line2D(
                    [0],
                    [0],
                    color=c_rc,
                    lw=1.5,
                    label=f"bias (RiCTO)={st_rc['bias']:.3f}",
                ),
                Line2D(
                    [0],
                    [0],
                    color=c_rc,
                    ls="--",
                    lw=1.2,
                    label="95% limits (RiCTO)",
                ),
            ]
        )

    # Single 2×4 legend: RiCTO (△) left, BoxMarker (○) right — snug columns
    combined_handles = list(rc_handles) + list(bm_handles)
    ncol_combined = 1
    if combined_handles:
        ncol_combined = max(1, (len(combined_handles) + 1) // 2)

    fig.tight_layout(rect=[0, 0, 1, 0.90])
    leg_cond = None
    if combined_handles:
        leg_cond = ax.legend(
            handles=combined_handles,
            ncol=ncol_combined,
            frameon=False,
            prop={"family": "Arial", "size": 9},
            loc="upper left",
            bbox_to_anchor=(0.01, 0.90),
            bbox_transform=fig.transFigure,
            borderaxespad=0.0,
            columnspacing=0.45,
            handletextpad=0.25,
        )
        ax.add_artist(leg_cond)
    if bias_handles:
        ax.legend(
            handles=bias_handles,
            frameon=False,
            prop={"family": "Arial", "size": 9},
            loc="upper right",
            bbox_to_anchor=(0.99, 0.90),
            bbox_transform=fig.transFigure,
            borderaxespad=0.0,
        )

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    if leg_cond is not None:
        bb = leg_cond.get_window_extent(renderer).transformed(fig.transFigure.inverted())
        n_bm = len(bm_handles)
        n_rc = len(rc_handles)
        n_tot = max(n_bm + n_rc, 1)
        # Left block = RiCTO, right block = BoxMarker
        rc_frac = n_rc / n_tot
        if n_rc:
            fig.text(
                bb.x0 + rc_frac * (bb.x1 - bb.x0) * 0.5,
                bb.y0 - 0.010,
                "RiCTO",
                ha="center",
                va="top",
                fontname="Arial",
                fontsize=10,
                color=_METHOD_LINE["RiCTO"],
            )
        if n_bm:
            fig.text(
                bb.x0 + (rc_frac + (1.0 - rc_frac) * 0.5) * (bb.x1 - bb.x0),
                bb.y0 - 0.010,
                "BoxMarker",
                ha="center",
                va="top",
                fontname="Arial",
                fontsize=10,
                color=_METHOD_LINE["BoxMarker"],
            )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def process_subject(namecode: str, *, dpi: int = 300) -> dict:
    rp = result_paths(namecode)
    long_path = stats_long_dir() / f"timing_abserr_{rp.sub_label}.csv"
    if not long_path.is_file():
        build_timing(namecode)
    # Rebuild from by_segment for mean of methods (GT and method times)
    from stats_io import ricto_summary_xlsx

    bs = pd.read_excel(ricto_summary_xlsx(rp.sub_label), sheet_name="by_segment")
    rows = []
    fig_paths = []
    model_dir = stats_models_dir()
    fig_dir = manuscript_figures_dir() / rp.sub_label
    fig_dir.mkdir(parents=True, exist_ok=True)

    contrasts = [
        ("RiCTO", "Grip", "ricto_onset", "gt_onset", "err_onset_s"),
        ("RiCTO", "Deposit", "ricto_offset", "gt_offset", "err_offset_s"),
        ("BoxMarker", "Grip", "marker_onset", "gt_onset", "err_marker_onset_s"),
        ("BoxMarker", "Deposit", "marker_offset", "gt_offset", "err_marker_offset_s"),
    ]
    for method, event, mcol, gcol, ecol in contrasts:
        cols = [mcol, gcol, ecol, "condition"]
        sub = bs[cols].dropna(subset=[mcol, gcol, ecol])
        if sub.empty:
            continue
        method_t = sub[mcol].to_numpy(dtype=float)
        gt_t = sub[gcol].to_numpy(dtype=float)
        diff = sub[ecol].to_numpy(dtype=float)
        mean_t = 0.5 * (method_t + gt_t)
        conds = sub["condition"].astype(str).to_numpy()
        st = bland_altman_stats(diff)
        rows.append(
            {
                "sub": rp.sub_label,
                "contrast": f"{method} - GT",
                "event": event,
                **st,
            }
        )
        tag = f"BlandAltman_{method}_{event}_{rp.sub_label}"
        png_ms = fig_dir / f"{tag}.png"
        png_model = model_dir / f"{tag}.png"
        written = plot_bland_altman(
            mean_t,
            diff,
            conditions=conds,
            title=f"{rp.sub_label} {method} vs GT ({event})",
            out_path=png_ms,
            dpi=dpi,
        )
        if written is not None:
            shutil.copy2(written, png_model)
            fig_paths.extend([str(png_ms), str(png_model)])

    # Combined BoxMarker (red ○) + RiCTO (blue △) vs GT; per-method bias/LoA on fig
    for event, r_m, b_m, gcol, r_e, b_e in (
        ("Grip", "ricto_onset", "marker_onset", "gt_onset", "err_onset_s", "err_marker_onset_s"),
        (
            "Deposit",
            "ricto_offset",
            "marker_offset",
            "gt_offset",
            "err_offset_s",
            "err_marker_offset_s",
        ),
    ):
        sub_r = bs[[r_m, gcol, r_e, "condition"]].dropna(subset=[r_m, gcol, r_e])
        sub_b = bs[[b_m, gcol, b_e, "condition"]].dropna(subset=[b_m, gcol, b_e])
        if sub_r.empty and sub_b.empty:
            continue
        mean_r = 0.5 * (
            sub_r[r_m].to_numpy(dtype=float) + sub_r[gcol].to_numpy(dtype=float)
        )
        diff_r = sub_r[r_e].to_numpy(dtype=float)
        cond_r = sub_r["condition"].astype(str).to_numpy()
        mean_b = 0.5 * (
            sub_b[b_m].to_numpy(dtype=float) + sub_b[gcol].to_numpy(dtype=float)
        )
        diff_b = sub_b[b_e].to_numpy(dtype=float)
        cond_b = sub_b["condition"].astype(str).to_numpy()
        tag = f"BlandAltman_Combined_{event}_{rp.sub_label}"
        png_ms = fig_dir / f"{tag}.png"
        png_model = model_dir / f"{tag}.png"
        written = plot_bland_altman_combined(
            mean_box=mean_b,
            diff_box=diff_b,
            cond_box=cond_b,
            mean_ricto=mean_r,
            diff_ricto=diff_r,
            cond_ricto=cond_r,
            title=f"{rp.sub_label} BoxMarker & RiCTO vs GT ({event})",
            out_path=png_ms,
            dpi=dpi,
        )
        if written is not None:
            shutil.copy2(written, png_model)
            fig_paths.extend([str(png_ms), str(png_model)])

    out_csv = model_dir / f"BlandAltman_timing_{rp.sub_label}.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    return {"table": str(out_csv), "figures": fig_paths, "n_contrasts": len(rows)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    args = ap.parse_args()
    print(process_subject(args.namecode))


if __name__ == "__main__":
    main()

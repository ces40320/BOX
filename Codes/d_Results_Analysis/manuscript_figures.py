# -*- coding: utf-8 -*-
"""Manuscript / report figures for RiCTO Results (dpi=300, APP_PLOT_STYLE)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RUN = _CODES / "c_Run_Tools"
_ESTATS = _CODES / "e_statistics"
for _p in (str(_CODES), str(_RUN), str(_HERE), str(_ESTATS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import (  # noqa: E402
    APP_PLOT_STYLE,
    EHF_APPS,
    EHF_AXES,
    L5S1_FORCE_AXES,
    L5S1_MOMENT_AXES,
    P_COLS,
    SECTIONS,
    analysis_asymmetric_root,
    result_paths,
    rows_to_matrix,
)
from stats_io import manuscript_figures_dir, ricto_summary_xlsx, stats_long_dir  # noqa: E402

MANUSCRIPT_DPI = 300


def _setup_ax(ax) -> None:
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(direction="in")


def _save(fig, out_path: Path, dpi: int = MANUSCRIPT_DPI) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    return out_path


def plot_ricto_optimization_triplet(
    namecode: str,
    *,
    condition: Optional[str] = None,
    seg: Optional[str] = None,
    dpi: int = MANUSCRIPT_DPI,
) -> Optional[Path]:
    """Fig-RiCTO-1: residual / EHF (vy L+R) / transfer schedule %."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import PATH_RULE as _path
    from optimization.ricto_io import read_opensim_storage

    rp = result_paths(namecode)
    ts_root = analysis_asymmetric_root() / "RiCTO" / "TimeSeries" / rp.sub_label
    if not ts_root.is_dir():
        return None
    files = sorted(ts_root.glob("*/*_RiCTO_timeseries.csv"))
    if not files:
        files = sorted(ts_root.rglob("*_RiCTO_timeseries.csv"))
    if not files:
        return None

    # pick representative: prefer requested, else first 10bpm AB-like
    chosen = None
    for f in files:
        name = f.name
        if condition and condition not in name:
            continue
        if seg and seg not in name:
            continue
        chosen = f
        break
    if chosen is None:
        for f in files:
            if "10bpm" in f.name and "AB" in f.name:
                chosen = f
                break
    if chosen is None:
        chosen = files[0]

    # parse cond/seg from filename: SUB7_15kg_10bpm_10AB_RiCTO_timeseries.csv
    stem = chosen.stem.replace("_RiCTO_timeseries", "")
    parts = stem.split("_")
    # SUB7, 15kg, 10bpm, 10AB
    cond = f"{parts[1]}_{parts[2]}" if len(parts) >= 4 else ""
    seg_id = parts[3] if len(parts) >= 4 else ""
    if condition:
        cond = condition
    if seg:
        seg_id = seg

    df = pd.read_csv(chosen)
    t = df["time"].to_numpy(dtype=float)
    residual = df["residual"].to_numpy(dtype=float)
    w_s = df["w_smooth"].to_numpy(dtype=float) if "w_smooth" in df.columns else np.zeros_like(t)
    w_r = df["w_rect"].to_numpy(dtype=float) if "w_rect" in df.columns else np.zeros_like(t)

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True, dpi=dpi)
    axes[0].plot(t, residual, color="0.2", lw=2.0)
    axes[0].set_ylabel("Pelvis residual (N)", fontname="Arial", fontsize=14)
    axes[0].set_title(
        f"Fig-RiCTO-1  {rp.sub_label}  {cond}  {seg_id}",
        fontname="Arial",
        fontsize=14,
    )
    _setup_ax(axes[0])

    # EHF panel: MeasuredEHF vs postRiCTO vertical (sum |Fy| style: raw vy L/R)
    cp = _path.ResultPaths(namecode).for_condition(cond)
    plotted = False
    for app in ("MeasuredEHF", "HeavyHand", "preRiCTO", "postRiCTO"):
        try:
            mot = cp.extload_path(seg_id, app)
        except Exception:
            continue
        p = Path(mot)
        if not p.is_file():
            continue
        try:
            mdf, _ = read_opensim_storage(p)
        except Exception:
            continue
        if "time" not in mdf.columns:
            continue
        sty = APP_PLOT_STYLE.get(app, {"color": "gray", "linestyle": "-", "label": app})
        for hand_col, lab in (
            ("hand_force3_vy", "L"),
            ("hand_force4_vy", "R"),
        ):
            if hand_col not in mdf.columns:
                continue
            axes[1].plot(
                mdf["time"].to_numpy(dtype=float),
                mdf[hand_col].to_numpy(dtype=float),
                color=sty["color"],
                linestyle=sty["linestyle"],
                lw=1.5 if lab == "L" else 1.0,
                alpha=0.9 if lab == "L" else 0.55,
                label=f"{sty['label']} {lab}",
            )
            plotted = True
    if not plotted:
        axes[1].text(0.5, 0.5, "ExtLoad not available", ha="center", transform=axes[1].transAxes)
    axes[1].set_ylabel("Hand Fy (N)", fontname="Arial", fontsize=14)
    axes[1].legend(frameon=False, prop={"family": "Arial", "size": 9}, ncol=2)
    _setup_ax(axes[1])

    axes[2].plot(t, 100.0 * w_r, color="darkorange", lw=2.0, label="preRiCTO (rect)")
    axes[2].plot(t, 100.0 * w_s, color="blue", lw=2.0, label="postRiCTO (smooth)")
    axes[2].set_ylabel("Load transfer (%)", fontname="Arial", fontsize=14)
    axes[2].set_xlabel("Time (s)", fontname="Arial", fontsize=14)
    axes[2].set_ylim(-5, 105)
    axes[2].legend(frameon=False, prop={"family": "Arial", "size": 11})
    _setup_ax(axes[2])

    fig.tight_layout()
    out = manuscript_figures_dir() / rp.sub_label / "Fig-RiCTO-1.png"
    _save(fig, out, dpi=dpi)
    plt.close(fig)
    return out


# Fig-RiCTO-2 style (manuscript)
_TIMING_METHOD_COLOR = {"RiCTO": "#6666FF", "BoxMarker": "#FF6666"}
_TIMING_METHOD_LABEL = {"RiCTO": "RiCTO", "BoxMarker": "Box Trajectory"}
_TIMING_AXIS_FONTSIZE = 28  # 2× prior 14 pt labels/ticks


def _ensure_timing_abserr_csv(namecode: str) -> Path:
    rp = result_paths(namecode)
    path = stats_long_dir() / f"timing_abserr_{rp.sub_label}.csv"
    if not path.is_file():
        from stats_timing_error import process_subject as _te

        _te(namecode)
    return path


def _draw_timing_abserr_bars(
    df: pd.DataFrame,
    *,
    title: str,
    out_path: Path,
    dpi: int = MANUSCRIPT_DPI,
) -> Optional[Path]:
    """Shared Fig-RiCTO-2 renderer (subject or SUBALL)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if df.empty or "abs_err_s" not in df.columns:
        return None

    # Left = Box Trajectory, right = RiCTO
    methods = [m for m in ("BoxMarker", "RiCTO") if m in set(df["method"])]
    if not methods:
        return None
    events = ["Grip", "Deposit"]
    x = np.arange(len(events))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 6), dpi=dpi)
    ymax = 0.0
    bar_x: list[float] = []
    bar_means: list[float] = []
    bar_stds: list[float] = []
    for i, method in enumerate(methods):
        means, stds = [], []
        for ev in events:
            sub = df[(df["method"] == method) & (df["event"] == ev)]["abs_err_s"]
            means.append(float(sub.mean()) if len(sub) else float("nan"))
            stds.append(float(sub.std(ddof=1)) if len(sub) > 1 else 0.0)
        means_a = np.asarray(means, dtype=float)
        stds_a = np.asarray(stds, dtype=float)
        xpos = x + (i - 0.5) * width
        ax.bar(
            xpos,
            means_a,
            width,
            color=_TIMING_METHOD_COLOR.get(method, "gray"),
            label=_TIMING_METHOD_LABEL.get(method, method),
            zorder=2,
        )
        for xi, m, s in zip(xpos, means_a, stds_a):
            if not (np.isfinite(m) and np.isfinite(s) and s > 0):
                continue
            bar_x.append(float(xi))
            bar_means.append(float(m))
            bar_stds.append(float(s))
        finite = np.isfinite(means_a) & np.isfinite(stds_a)
        if finite.any():
            ymax = max(ymax, float(np.nanmax(means_a[finite] + stds_a[finite])))

    # SD whiskers: upward from bar top only (no downward segment)
    cap_half = 0.06
    for xi, m, s in zip(bar_x, bar_means, bar_stds):
        ax.vlines(xi, m, m + s, colors="k", linewidth=1.2, zorder=3)
        ax.hlines(m + s, xi - cap_half, xi + cap_half, colors="k", linewidth=1.2, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(events, fontname="Arial", fontsize=_TIMING_AXIS_FONTSIZE)
    ax.set_ylabel(
        "Absolute Timing Error (s)",
        fontname="Arial",
        fontsize=_TIMING_AXIS_FONTSIZE,
    )
    ax.set_title(title, fontname="Arial", fontsize=14)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 11})
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    top = ymax * 1.08 if ymax > 0 else 1.0
    ax.set_ylim(0.0, top)
    ax.yaxis.set_major_locator(plt.MultipleLocator(0.2))
    ax.tick_params(
        axis="both",
        which="major",
        direction="out",
        length=6,
        width=1.0,
        labelsize=_TIMING_AXIS_FONTSIZE,
        bottom=True,
        top=False,
        left=True,
        right=False,
    )
    for lab in list(ax.get_yticklabels()) + list(ax.get_xticklabels()):
        lab.set_fontname("Arial")
    fig.tight_layout()
    ax.set_ylim(0.0, top)
    ax.tick_params(axis="both", which="major", direction="out", length=6)
    _save(fig, out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def plot_timing_abserr_bars(namecode: str, *, dpi: int = MANUSCRIPT_DPI) -> Optional[Path]:
    """Fig-RiCTO-2: Grip/Deposit absolute error by method."""
    rp = result_paths(namecode)
    path = _ensure_timing_abserr_csv(namecode)
    df = pd.read_csv(path)
    out = manuscript_figures_dir() / rp.sub_label / "Fig-RiCTO-2.png"
    return _draw_timing_abserr_bars(
        df,
        title=f"Fig-RiCTO-2  {rp.sub_label} vs GT 5 N window",
        out_path=out,
        dpi=dpi,
    )


def _load_timing_abserr_suball(
    roster: Optional[Sequence[dict]] = None,
) -> Tuple[pd.DataFrame, list[str]]:
    """Stack timing abs-error long tables for SUBALL-eligible subjects.

    Aggregation unit matches per-subject Fig-RiCTO-2: all segment rows pooled,
    then mean±SD. Returns (stacked_df, used_sub_labels).
    """
    from stats_io import suball_namecodes

    rows = list(roster) if roster is not None else suball_namecodes()
    frames: list[pd.DataFrame] = []
    used: list[str] = []
    for e in rows:
        nc = e.get("namecode")
        sub = e.get("sub_label") or (f"SUB{e.get('SUB')}" if e.get("SUB") is not None else None)
        if not nc:
            continue
        path = _ensure_timing_abserr_csv(str(nc))
        if not path.is_file():
            continue
        part = pd.read_csv(path)
        if part.empty:
            continue
        if sub:
            part = part.copy()
            part["sub_label"] = str(sub)
            used.append(str(sub))
        frames.append(part)
    if not frames:
        return pd.DataFrame(), []
    return pd.concat(frames, ignore_index=True), used


def process_suball_timing_figure(*, dpi: int = MANUSCRIPT_DPI) -> dict:
    """Write SUBALL Fig-RiCTO-2 under ``_figures/RiCTO_manuscript/SUBALL/``."""
    write_manuscript_readme()
    df, used = _load_timing_abserr_suball()
    path: Optional[Path] = None
    if not df.empty:
        stack_path = stats_long_dir() / "timing_abserr_SUBALL.csv"
        df.to_csv(stack_path, index=False)
        out = manuscript_figures_dir() / "SUBALL" / "Fig-RiCTO-2.png"
        path = _draw_timing_abserr_bars(
            df,
            title=f"Fig-RiCTO-2  SUBALL vs GT 5 N window (n={len(used)})",
            out_path=out,
            dpi=dpi,
        )
    return {
        "Fig-RiCTO-2": str(path) if path is not None else "",
        "subjects": used,
    }


def plot_timing_abserr_bars_suball(*, dpi: int = MANUSCRIPT_DPI) -> Optional[Path]:
    """Fig-RiCTO-2 for SUBALL: mean±SD across eligible subjects' timing rows."""
    out = process_suball_timing_figure(dpi=dpi).get("Fig-RiCTO-2") or ""
    return Path(out) if out else None


def _load_ehf_matrices(
    sub_label: str, axis: str, hand: str = "L", section: str = "AB"
) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {}
    for app in EHF_APPS:
        path = (
            analysis_asymmetric_root()
            / "EHF"
            / app
            / axis
            / f"{sub_label}_{hand}_{section}.csv"
        )
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        rows = df.to_dict("records")
        out[app] = rows_to_matrix(rows)
    return out


def _rmse_quartile_means(sub_label: str, axis: str, hand: str = "L") -> pd.DataFrame:
    path = (
        analysis_asymmetric_root()
        / "EHF"
        / "MeasuredEHF"
        / "_metrics"
        / f"RMSE_all_apps_{sub_label}.csv"
    )
    if not path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df = df[(df["axis"] == axis) & (df["hand"] == hand)]
    return (
        df.groupby("app", as_index=False)[["RMSE_q1", "RMSE_q2", "RMSE_q3", "RMSE_q4"]]
        .mean()
    )


def plot_ehf_resultant_rmse_panel(
    namecode: str,
    *,
    axis: str = "Resultant",
    hand: str = "L",
    section: str = "AB",
    fig_id: str = "Fig-EHF-1",
    dpi: int = MANUSCRIPT_DPI,
) -> Optional[Path]:
    """mean±std timeseries + Q1–Q4 RMSE bars."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rp = result_paths(namecode)
    series = _load_ehf_matrices(rp.sub_label, axis, hand=hand, section=section)
    if not series:
        return None
    qdf = _rmse_quartile_means(rp.sub_label, axis, hand=hand)

    fig, (ax0, ax1) = plt.subplots(
        2, 1, figsize=(10, 9), dpi=dpi, gridspec_kw={"height_ratios": [2.2, 1.0]}
    )
    x = np.linspace(0, 100, len(P_COLS))
    for app, arr in series.items():
        if arr.size == 0:
            continue
        sty = APP_PLOT_STYLE.get(app, {"color": "gray", "linestyle": "-", "label": app})
        mean = np.nanmean(arr, axis=0)
        std = np.nanstd(arr, axis=0)
        ax0.plot(x, mean, color=sty["color"], ls=sty["linestyle"], lw=2.0, label=sty["label"])
        ax0.fill_between(x, mean - std, mean + std, color=sty["color"], alpha=0.15)
    ax0.set_xlabel("Time (%)", fontname="Arial", fontsize=14)
    ax0.set_ylabel(f"EHF {axis} (N)", fontname="Arial", fontsize=14)
    ax0.set_title(
        f"{fig_id} {axis} {hand} {section} ({rp.sub_label})",
        fontname="Arial",
        fontsize=14,
    )
    ax0.legend(frameon=False, prop={"family": "Arial", "size": 11})
    _setup_ax(ax0)

    if not qdf.empty:
        apps = [a for a in EHF_APPS if a in set(qdf["app"]) and a != "MeasuredEHF"]
        qs = ["RMSE_q1", "RMSE_q2", "RMSE_q3", "RMSE_q4"]
        xpos = np.arange(len(qs))
        width = 0.2
        for i, app in enumerate(apps):
            row = qdf[qdf["app"] == app]
            if row.empty:
                continue
            vals = [float(row.iloc[0][q]) for q in qs]
            sty = APP_PLOT_STYLE.get(app, {"color": "gray", "label": app})
            ax1.bar(
                xpos + (i - len(apps) / 2) * width + width / 2,
                vals,
                width,
                color=sty["color"],
                label=sty["label"],
            )
        ax1.set_xticks(xpos)
        ax1.set_xticklabels(["Q1", "Q2", "Q3", "Q4"])
        ax1.set_ylabel("RMSE (N)", fontname="Arial", fontsize=14)
        ax1.legend(frameon=False, prop={"family": "Arial", "size": 10}, ncol=3)
        _setup_ax(ax1)

    fig.tight_layout()
    out = manuscript_figures_dir() / rp.sub_label / f"{fig_id}.png"
    _save(fig, out, dpi=dpi)
    plt.close(fig)
    return out


_G = 9.80665  # m/s^2 — convert force (N) → % body weight


def _body_mass_kg_for_sub(sub_label: str) -> Optional[float]:
    info = _anthro_for_sub(sub_label)
    return info.get("body_mass_kg") if info else None


def _anthro_for_sub(sub_label: str) -> Optional[dict]:
    """Return ``{body_mass_kg, height_m}`` from ``SUB_Info`` (height stored as mm)."""
    import SUB_Info as _sub_info

    want = str(sub_label).upper().replace("SUB", "")
    for _nc, info in _sub_info.subjects.items():
        if str(info.get("SUB_number")) != want:
            continue
        bm = info.get("body_mass")
        ht = info.get("height")
        if bm is None:
            return None
        height_m = float(ht) / 1000.0 if ht is not None else None
        return {"body_mass_kg": float(bm), "height_m": height_m}
    return None


def _n_to_pct_bw(arr: np.ndarray, body_mass_kg: float) -> np.ndarray:
    return np.asarray(arr, dtype=float) / (float(body_mass_kg) * _G) * 100.0


def _nm_to_pct_bw_h(
    arr: np.ndarray, body_mass_kg: float, height_m: float
) -> np.ndarray:
    """Moment (N·m) → % of (BW × height): M / (m g h) × 100."""
    return (
        np.asarray(arr, dtype=float)
        / (float(body_mass_kg) * _G * float(height_m))
        * 100.0
    )


def _ehf_suball_roster() -> list[dict]:
    """Same eligibility as ``_figures/EHF/SUBALL`` mean±std rebuild."""
    from figure_outputs import (
        filter_eligible_with_analysis,
        load_pipeline_eligible_subjects,
    )

    eligible = load_pipeline_eligible_subjects()
    try:
        eligible = filter_eligible_with_analysis(
            "EHF", eligible, axes=EHF_AXES, hands=("L", "R")
        )
    except TypeError:
        eligible = filter_eligible_with_analysis("EHF", eligible)
    out = []
    for e in eligible:
        sub = e.get("sub_label") or f"SUB{e.get('SUB')}"
        nc = e.get("namecode")
        bm = _body_mass_kg_for_sub(str(sub))
        if not nc or bm is None:
            continue
        out.append({"namecode": nc, "sub_label": str(sub), "body_mass_kg": bm})
    return out


def _load_ehf_suball_bw_series(
    axis: str, hand: str, section: str, roster: Sequence[dict]
) -> Tuple[Dict[str, np.ndarray], list[str]]:
    """Stack BW-normalized (%BW) timeseries rows across SUBALL subjects."""
    by_app: Dict[str, list] = {a: [] for a in EHF_APPS}
    used: list[str] = []
    for e in roster:
        sub = e["sub_label"]
        bm = float(e["body_mass_kg"])
        mats = _load_ehf_matrices(sub, axis, hand=hand, section=section)
        if not mats:
            continue
        used.append(sub)
        for app, arr in mats.items():
            if arr.size == 0:
                continue
            by_app[app].append(_n_to_pct_bw(arr, bm))
    stacked = {
        a: np.vstack(chunks) for a, chunks in by_app.items() if chunks
    }
    return stacked, used


def _rmse_quartile_bw_mean_std(
    axis: str,
    hand: str,
    roster: Sequence[dict],
    *,
    section: Optional[str] = None,
) -> pd.DataFrame:
    """Per-app Q1–Q4 RMSE in %BW: mean and SD across SUBALL segments."""
    qs = ["RMSE_q1", "RMSE_q2", "RMSE_q3", "RMSE_q4"]
    frames: list[pd.DataFrame] = []
    for e in roster:
        sub = e["sub_label"]
        bm = float(e["body_mass_kg"])
        path = (
            analysis_asymmetric_root()
            / "EHF"
            / "MeasuredEHF"
            / "_metrics"
            / f"RMSE_all_apps_{sub}.csv"
        )
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        df = df[(df["axis"] == axis) & (df["hand"] == hand)].copy()
        if section is not None and "section" in df.columns:
            df = df[df["section"].astype(str) == str(section)]
        if df.empty:
            continue
        for q in qs:
            df[q] = _n_to_pct_bw(df[q].to_numpy(dtype=float), bm)
        df["sub"] = sub
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    all_df = pd.concat(frames, ignore_index=True)
    g = all_df.groupby("app", as_index=False)
    means = g[qs].mean().rename(columns={q: f"{q}_mean" for q in qs})
    stds = g[qs].std(ddof=1).rename(columns={q: f"{q}_std" for q in qs})
    return means.merge(stds, on="app")


def plot_ehf_suball_bw_panel(
    *,
    axis: str = "Resultant",
    hand: str = "L",
    section: str = "AB",
    fig_id: str = "Fig-EHF-1",
    dpi: int = MANUSCRIPT_DPI,
    roster: Optional[Sequence[dict]] = None,
) -> Optional[Path]:
    """SUBALL Fig-EHF panel: %BW mean±std curves + Q RMSE mean±SD bars.

    Saves under ``Analysis/Asymmetric/_figures/EHF/SUBALL/``.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from figure_outputs import figures_suball_dir

    roster_list = list(roster) if roster is not None else _ehf_suball_roster()
    if not roster_list:
        return None
    series, used = _load_ehf_suball_bw_series(axis, hand, section, roster_list)
    if not series:
        return None
    qdf = _rmse_quartile_bw_mean_std(axis, hand, roster_list, section=section)

    fig, (ax0, ax1) = plt.subplots(
        2, 1, figsize=(10, 9), dpi=dpi, gridspec_kw={"height_ratios": [2.2, 1.0]}
    )
    x = np.linspace(0, 100, len(P_COLS))
    for app, arr in series.items():
        if arr.size == 0:
            continue
        sty = APP_PLOT_STYLE.get(app, {"color": "gray", "linestyle": "-", "label": app})
        mean = np.nanmean(arr, axis=0)
        std = np.nanstd(arr, axis=0)
        ax0.plot(x, mean, color=sty["color"], ls=sty["linestyle"], lw=2.0, label=sty["label"])
        ax0.fill_between(x, mean - std, mean + std, color=sty["color"], alpha=0.15)
    ax0.set_xlabel("Time (%)", fontname="Arial", fontsize=14)
    ax0.set_ylabel(f"EHF {axis} (%BW)", fontname="Arial", fontsize=14)
    # Match _figures/EHF/SUBALL naming: "{axis} {hand} {section} (SUBALL n=…)"
    stem = f"{axis}_{hand}_{section}"
    n_sub = len(set(used))
    ax0.set_title(
        f"{fig_id} {stem.replace('_', ' ')} (SUBALL n={n_sub})",
        fontname="Arial",
        fontsize=14,
    )
    ax0.legend(frameon=False, prop={"family": "Arial", "size": 11})
    _setup_ax(ax0)

    if not qdf.empty:
        apps = [a for a in EHF_APPS if a in set(qdf["app"]) and a != "MeasuredEHF"]
        qs = ["RMSE_q1", "RMSE_q2", "RMSE_q3", "RMSE_q4"]
        xpos = np.arange(len(qs))
        width = 0.2
        for i, app in enumerate(apps):
            row = qdf[qdf["app"] == app]
            if row.empty:
                continue
            vals = [float(row.iloc[0][f"{q}_mean"]) for q in qs]
            errs = [
                float(row.iloc[0][f"{q}_std"])
                if pd.notna(row.iloc[0][f"{q}_std"])
                else 0.0
                for q in qs
            ]
            sty = APP_PLOT_STYLE.get(app, {"color": "gray", "label": app})
            ax1.bar(
                xpos + (i - len(apps) / 2) * width + width / 2,
                vals,
                width,
                yerr=errs,
                color=sty["color"],
                label=sty["label"],
                capsize=3,
                error_kw={"elinewidth": 1.0, "capthick": 1.0},
            )
        ax1.set_xticks(xpos)
        ax1.set_xticklabels(["Q1", "Q2", "Q3", "Q4"])
        ax1.set_ylabel("RMSE (%BW)", fontname="Arial", fontsize=14)
        ax1.set_ylim(bottom=0.0)
        ax1.legend(frameon=False, prop={"family": "Arial", "size": 10}, ncol=3)
        _setup_ax(ax1)

    fig.tight_layout()
    # e.g. SUBALL_Fig-EHF-1_Resultant_L_AB.png (axis visible in filename)
    out = figures_suball_dir("EHF") / f"SUBALL_{fig_id}_{stem}.png"
    _save(fig, out, dpi=dpi)
    plt.close(fig)
    return out


def process_suball_ehf_figures(*, dpi: int = MANUSCRIPT_DPI) -> dict:
    """Write Fig-EHF-1..4 (BW-normalized) for AB/BC/CA to ``_figures/EHF/SUBALL/``."""
    roster = _ehf_suball_roster()
    specs = [
        ("Fig-EHF-1", "Resultant"),
        ("Fig-EHF-2", "AP"),
        ("Fig-EHF-3", "ML"),
        ("Fig-EHF-4", "Vertical"),
    ]
    outs: dict = {
        "roster": [
            {"sub_label": e["sub_label"], "namecode": e["namecode"]} for e in roster
        ]
    }
    for section in SECTIONS:
        for fig_id, axis in specs:
            key = f"{fig_id}_{section}"
            outs[key] = plot_ehf_suball_bw_panel(
                axis=axis,
                section=section,
                fig_id=fig_id,
                dpi=dpi,
                roster=roster,
            )
    return {
        "roster": outs["roster"],
        **{
            k: ("" if v is None else str(v))
            for k, v in outs.items()
            if k != "roster"
        },
    }


def _l5s1_is_force(axis: str) -> bool:
    return str(axis).startswith("Force_")


def _l5s1_norm_unit(axis: str) -> str:
    return "%BW" if _l5s1_is_force(axis) else "%BW·H"


def _l5s1_norm_label(axis: str) -> str:
    """Shared domain label: JRF (force) / JRM (moment)."""
    if _l5s1_is_force(axis):
        return f"L5S1 JRF {axis.replace('Force_', '', 1)}"
    return f"L5S1 JRM {axis.replace('Moment_', '', 1)}"


def _l5s1_normalize_arr(arr: np.ndarray, axis: str, e: dict) -> np.ndarray:
    bm = float(e["body_mass_kg"])
    if _l5s1_is_force(axis):
        return _n_to_pct_bw(arr, bm)
    ht = e.get("height_m")
    if ht is None:
        raise ValueError(f"height_m required for moment normalization ({e})")
    return _nm_to_pct_bw_h(arr, bm, float(ht))


def _l5s1_suball_roster() -> list[dict]:
    """Same eligibility as ``_figures/L5S1/SUBALL`` mean±std rebuild."""
    from figure_outputs import (
        filter_eligible_with_analysis,
        load_pipeline_eligible_subjects,
    )

    axes = tuple(L5S1_FORCE_AXES) + tuple(L5S1_MOMENT_AXES)
    eligible = load_pipeline_eligible_subjects()
    try:
        eligible = filter_eligible_with_analysis("L5S1", eligible, axes=axes)
    except TypeError:
        eligible = filter_eligible_with_analysis("L5S1", eligible)
    out = []
    for e in eligible:
        sub = e.get("sub_label") or f"SUB{e.get('SUB')}"
        nc = e.get("namecode")
        anthro = _anthro_for_sub(str(sub))
        if not nc or anthro is None or anthro.get("height_m") is None:
            continue
        out.append(
            {
                "namecode": nc,
                "sub_label": str(sub),
                "body_mass_kg": anthro["body_mass_kg"],
                "height_m": anthro["height_m"],
            }
        )
    return out


def _load_l5s1_suball_bw_series(
    axis: str, section: str, roster: Sequence[dict]
) -> Tuple[Dict[str, np.ndarray], list[str]]:
    by_app: Dict[str, list] = {a: [] for a in EHF_APPS}
    used: list[str] = []
    for e in roster:
        sub = e["sub_label"]
        mats = _load_l5s1_matrices(sub, axis=axis, section=section)
        if not mats:
            continue
        used.append(sub)
        for app, arr in mats.items():
            if arr.size == 0:
                continue
            by_app[app].append(_l5s1_normalize_arr(arr, axis, e))
    stacked = {a: np.vstack(chunks) for a, chunks in by_app.items() if chunks}
    return stacked, used


def _rmse_l5s1_quartile_bw_mean_std(
    axis: str,
    roster: Sequence[dict],
    *,
    section: Optional[str] = None,
) -> pd.DataFrame:
    """Per-app Q1–Q4 RMSE in %BW or %BW·H across SUBALL segments."""
    qs = ["RMSE_q1", "RMSE_q2", "RMSE_q3", "RMSE_q4"]
    frames: list[pd.DataFrame] = []
    for e in roster:
        sub = e["sub_label"]
        path = (
            analysis_asymmetric_root()
            / "L5S1"
            / "MeasuredEHF"
            / "_metrics"
            / f"RMSE_all_apps_{sub}.csv"
        )
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        df = df[df["axis"] == axis].copy()
        if section is not None and "section" in df.columns:
            df = df[df["section"].astype(str) == str(section)]
        if df.empty:
            continue
        for q in qs:
            df[q] = _l5s1_normalize_arr(df[q].to_numpy(dtype=float), axis, e)
        df["sub"] = sub
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    all_df = pd.concat(frames, ignore_index=True)
    g = all_df.groupby("app", as_index=False)
    means = g[qs].mean().rename(columns={q: f"{q}_mean" for q in qs})
    stds = g[qs].std(ddof=1).rename(columns={q: f"{q}_std" for q in qs})
    return means.merge(stds, on="app")


def plot_l5s1_suball_bw_panel(
    *,
    axis: str = "Force_Resultant",
    section: str = "AB",
    fig_id: str = "Fig-L5S1-F1",
    dpi: int = MANUSCRIPT_DPI,
    roster: Optional[Sequence[dict]] = None,
) -> Optional[Path]:
    """SUBALL L5S1 panel: BW-normalized mean±std + Q RMSE mean±SD bars.

    Force → %BW; Moment → %BW·H (M / (m g h) × 100).
    Saves under ``Analysis/Asymmetric/_figures/L5S1/SUBALL/``.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from figure_outputs import figures_suball_dir

    roster_list = list(roster) if roster is not None else _l5s1_suball_roster()
    if not roster_list:
        return None
    series, used = _load_l5s1_suball_bw_series(axis, section, roster_list)
    if not series:
        return None
    qdf = _rmse_l5s1_quartile_bw_mean_std(axis, roster_list, section=section)
    unit = _l5s1_norm_unit(axis)

    fig, (ax0, ax1) = plt.subplots(
        2, 1, figsize=(10, 9), dpi=dpi, gridspec_kw={"height_ratios": [2.2, 1.0]}
    )
    x = np.linspace(0, 100, len(P_COLS))
    for app, arr in series.items():
        if arr.size == 0:
            continue
        sty = APP_PLOT_STYLE.get(app, {"color": "gray", "linestyle": "-", "label": app})
        mean = np.nanmean(arr, axis=0)
        std = np.nanstd(arr, axis=0)
        ax0.plot(x, mean, color=sty["color"], ls=sty["linestyle"], lw=2.0, label=sty["label"])
        ax0.fill_between(x, mean - std, mean + std, color=sty["color"], alpha=0.15)
    ax0.set_xlabel("Time (%)", fontname="Arial", fontsize=14)
    ax0.set_ylabel(f"{_l5s1_norm_label(axis)} ({unit})", fontname="Arial", fontsize=14)
    stem = f"{axis}_{section}"
    n_sub = len(set(used))
    ax0.set_title(
        f"{fig_id} {stem.replace('_', ' ')} (SUBALL n={n_sub})",
        fontname="Arial",
        fontsize=14,
    )
    ax0.legend(frameon=False, prop={"family": "Arial", "size": 11})
    _setup_ax(ax0)

    if not qdf.empty:
        apps = [a for a in EHF_APPS if a in set(qdf["app"]) and a != "MeasuredEHF"]
        qs = ["RMSE_q1", "RMSE_q2", "RMSE_q3", "RMSE_q4"]
        xpos = np.arange(len(qs))
        width = 0.2
        for i, app in enumerate(apps):
            row = qdf[qdf["app"] == app]
            if row.empty:
                continue
            vals = [float(row.iloc[0][f"{q}_mean"]) for q in qs]
            errs = [
                float(row.iloc[0][f"{q}_std"])
                if pd.notna(row.iloc[0][f"{q}_std"])
                else 0.0
                for q in qs
            ]
            sty = APP_PLOT_STYLE.get(app, {"color": "gray", "label": app})
            ax1.bar(
                xpos + (i - len(apps) / 2) * width + width / 2,
                vals,
                width,
                yerr=errs,
                color=sty["color"],
                label=sty["label"],
                capsize=3,
                error_kw={"elinewidth": 1.0, "capthick": 1.0},
            )
        ax1.set_xticks(xpos)
        ax1.set_xticklabels(["Q1", "Q2", "Q3", "Q4"])
        ax1.set_ylabel(f"RMSE ({unit})", fontname="Arial", fontsize=14)
        ax1.set_ylim(bottom=0.0)
        ax1.legend(frameon=False, prop={"family": "Arial", "size": 10}, ncol=3)
        _setup_ax(ax1)

    fig.tight_layout()
    out = figures_suball_dir("L5S1") / f"SUBALL_{fig_id}_{stem}.png"
    _save(fig, out, dpi=dpi)
    plt.close(fig)
    return out


def process_suball_l5s1_figures(*, dpi: int = MANUSCRIPT_DPI) -> dict:
    """Write Fig-L5S1 F1–F4 / M1–M3 (BW-normalized) for AB/BC/CA."""
    roster = _l5s1_suball_roster()
    specs = [
        ("Fig-L5S1-F1", "Force_Resultant"),
        ("Fig-L5S1-F2", "Force_AP"),
        ("Fig-L5S1-F3", "Force_ML"),
        ("Fig-L5S1-F4", "Force_Vertical"),
        ("Fig-L5S1-M1", "Moment_FlexionExtension"),
        ("Fig-L5S1-M2", "Moment_LateralBending"),
        ("Fig-L5S1-M3", "Moment_AxialRotation"),
    ]
    outs: dict = {
        "roster": [
            {"sub_label": e["sub_label"], "namecode": e["namecode"]} for e in roster
        ]
    }
    for section in SECTIONS:
        for fig_id, axis in specs:
            key = f"{fig_id}_{section}"
            outs[key] = plot_l5s1_suball_bw_panel(
                axis=axis,
                section=section,
                fig_id=fig_id,
                dpi=dpi,
                roster=roster,
            )
    return {
        "roster": outs["roster"],
        **{
            k: ("" if v is None else str(v))
            for k, v in outs.items()
            if k != "roster"
        },
    }


def _load_l5s1_matrices(
    sub_label: str, axis: str = "Force_Resultant", section: str = "AB"
) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {}
    for app in EHF_APPS:
        path = analysis_asymmetric_root() / "L5S1" / app / axis / f"{sub_label}_{section}.csv"
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        out[app] = rows_to_matrix(df.to_dict("records"))
    return out


def plot_l5s1_force_panel(
    namecode: str,
    *,
    axis: str = "Force_Resultant",
    section: str = "AB",
    dpi: int = MANUSCRIPT_DPI,
) -> Optional[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rp = result_paths(namecode)
    series = _load_l5s1_matrices(rp.sub_label, axis=axis, section=section)
    if not series:
        return None
    fig, ax = plt.subplots(figsize=(10, 7), dpi=dpi)
    x = np.linspace(0, 100, len(P_COLS))
    for app, arr in series.items():
        sty = APP_PLOT_STYLE.get(app, {"color": "gray", "linestyle": "-", "label": app})
        mean = np.nanmean(arr, axis=0)
        std = np.nanstd(arr, axis=0)
        ax.plot(x, mean, color=sty["color"], ls=sty["linestyle"], lw=2.0, label=sty["label"])
        ax.fill_between(x, mean - std, mean + std, color=sty["color"], alpha=0.15)
    ax.set_xlabel("Time (%)", fontname="Arial", fontsize=14)
    ax.set_ylabel("L5/S1 force (N)", fontname="Arial", fontsize=14)
    ax.set_title(f"Fig-L5S1-1  {rp.sub_label}  {axis}  {section}", fontname="Arial", fontsize=14)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 11})
    _setup_ax(ax)
    fig.tight_layout()
    out = manuscript_figures_dir() / rp.sub_label / "Fig-L5S1-1.png"
    _save(fig, out, dpi=dpi)
    plt.close(fig)
    return out


def plot_l5s1_peak_panel(namecode: str, *, dpi: int = MANUSCRIPT_DPI) -> Optional[Path]:
    """Fig-L5S1-2: initial/final peak magnitude bars by app."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from stats_rm_anova import build_l5s1_peaks

    rp = result_paths(namecode)
    peaks = build_l5s1_peaks(namecode)
    if peaks.empty:
        return None
    apps = [a for a in EHF_APPS if a in set(peaks["app"])]
    metrics = [
        ("initial_peak_mag", "Initial peak"),
        ("final_peak_mag", "Final peak"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), dpi=dpi, sharey=True)
    x = np.arange(len(metrics))
    width = 0.18
    for i, app in enumerate(apps):
        sty = APP_PLOT_STYLE.get(app, {"color": "gray", "label": app})
        vals = []
        errs = []
        for col, _ in metrics:
            s = peaks.loc[peaks["app"] == app, col]
            vals.append(float(s.mean()) if len(s) else float("nan"))
            errs.append(float(s.std(ddof=1)) if len(s) > 1 else 0.0)
        axes[0].bar(
            x + (i - len(apps) / 2) * width + width / 2,
            vals,
            width,
            yerr=errs,
            color=sty["color"],
            label=sty["label"],
            capsize=3,
        )
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([m[1] for m in metrics])
    axes[0].set_ylabel("Peak magnitude (N)", fontname="Arial", fontsize=14)
    axes[0].set_title(f"Fig-L5S1-2  {rp.sub_label} peaks", fontname="Arial", fontsize=14)
    axes[0].legend(frameon=False, prop={"family": "Arial", "size": 9})
    _setup_ax(axes[0])

    # peak time dots
    for i, app in enumerate(apps):
        sty = APP_PLOT_STYLE.get(app, {"color": "gray", "label": app})
        for j, col in enumerate(("initial_peak_time_pct", "final_peak_time_pct")):
            s = peaks.loc[peaks["app"] == app, col].dropna()
            if s.empty:
                continue
            axes[1].scatter(
                np.full(len(s), j) + (i - len(apps) / 2) * 0.12,
                s,
                c=sty["color"],
                s=18,
                alpha=0.55,
                label=sty["label"] if j == 0 else None,
            )
    axes[1].set_xticks([0, 1])
    axes[1].set_xticklabels(["Initial time", "Final time"])
    axes[1].set_ylabel("Peak time (%)", fontname="Arial", fontsize=14)
    axes[1].set_ylim(-5, 105)
    _setup_ax(axes[1])
    fig.tight_layout()
    out = manuscript_figures_dir() / rp.sub_label / "Fig-L5S1-2.png"
    _save(fig, out, dpi=dpi)
    plt.close(fig)
    return out


def write_manuscript_readme() -> Path:
    root = manuscript_figures_dir()
    text = """# RiCTO manuscript figures

Official / report-ready copies (dpi 300). Regenerable pipeline plots remain under `_figures/{EHF,L5S1,Residual}/`.

| ID | Script | Data |
|----|--------|------|
| Fig-RiCTO-1 | `manuscript_figures.plot_ricto_optimization_triplet` | RiCTO TimeSeries + ExtLoad |
| Fig-RiCTO-2 | `manuscript_figures.plot_timing_abserr_bars` | `_stats/long/timing_abserr_*.csv` |
| Fig-RiCTO-2 (SUBALL) | `manuscript_figures.process_suball_timing_figure` | stacked `timing_abserr_SUBALL.csv` → `RiCTO_manuscript/SUBALL/` |
| Fig-EHF-1..4 | `manuscript_figures.plot_ehf_resultant_rmse_panel` | EHF timeseries + RMSE_all_apps |
| Fig-EHF-1..4 (SUBALL) | `manuscript_figures.process_suball_ehf_figures` | BW-normalized (%BW) → `_figures/EHF/SUBALL/` |
| Fig-L5S1-1 | `manuscript_figures.plot_l5s1_force_panel` | L5S1 Force_Resultant |
| Fig-L5S1-2 | `manuscript_figures.plot_l5s1_peak_panel` | L5S1 peaks long table |

Style: Arial 14/11, `APP_PLOT_STYLE` (MeasuredEHF black dashed, HeavyHand red, preRiCTO darkorange, postRiCTO blue). Fig-RiCTO-2: RiCTO `#6666FF`, Box Trajectory `#FF6666`, axis fonts 28 pt.
"""
    path = root / "README.md"
    path.write_text(text, encoding="utf-8")
    return path


def process_subject(namecode: str) -> dict:
    write_manuscript_readme()
    outs = {
        "Fig-RiCTO-1": plot_ricto_optimization_triplet(namecode),
        "Fig-RiCTO-2": plot_timing_abserr_bars(namecode),
        "Fig-EHF-1": plot_ehf_resultant_rmse_panel(
            namecode, axis="Resultant", fig_id="Fig-EHF-1"
        ),
        "Fig-EHF-2": plot_ehf_resultant_rmse_panel(
            namecode, axis="AP", fig_id="Fig-EHF-2"
        ),
        "Fig-EHF-3": plot_ehf_resultant_rmse_panel(
            namecode, axis="ML", fig_id="Fig-EHF-3"
        ),
        "Fig-EHF-4": plot_ehf_resultant_rmse_panel(
            namecode, axis="Vertical", fig_id="Fig-EHF-4"
        ),
        "Fig-L5S1-1": plot_l5s1_force_panel(namecode),
        "Fig-L5S1-2": plot_l5s1_peak_panel(namecode),
    }
    return {k: str(v) if v is not None else "" for k, v in outs.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument(
        "--suball-ehf",
        action="store_true",
        help="Write BW-normalized Fig-EHF-1..4 to _figures/EHF/SUBALL",
    )
    ap.add_argument(
        "--suball-l5s1",
        action="store_true",
        help="Write BW-normalized Fig-L5S1 F/M panels to _figures/L5S1/SUBALL",
    )
    ap.add_argument(
        "--suball-timing",
        action="store_true",
        help="Write Fig-RiCTO-2 to _figures/RiCTO_manuscript/SUBALL",
    )
    args = ap.parse_args()
    if args.suball_ehf:
        print(process_suball_ehf_figures())
    elif args.suball_l5s1:
        print(process_suball_l5s1_figures())
    elif args.suball_timing:
        print(process_suball_timing_figure())
    else:
        print(process_subject(args.namecode))


if __name__ == "__main__":
    main()

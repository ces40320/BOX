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


def plot_timing_abserr_bars(namecode: str, *, dpi: int = MANUSCRIPT_DPI) -> Optional[Path]:
    """Fig-RiCTO-2: Grip/Deposit absolute error by method."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rp = result_paths(namecode)
    path = stats_long_dir() / f"timing_abserr_{rp.sub_label}.csv"
    if not path.is_file():
        from stats_timing_error import process_subject as _te

        _te(namecode)
    df = pd.read_csv(path)
    if df.empty:
        return None

    methods = [m for m in ("RiCTO", "BoxMarker") if m in set(df["method"])]
    events = ["Grip", "Deposit"]
    x = np.arange(len(events))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 6), dpi=dpi)
    colors = {"RiCTO": "blue", "BoxMarker": "0.45"}
    for i, method in enumerate(methods):
        means, stds = [], []
        for ev in events:
            sub = df[(df["method"] == method) & (df["event"] == ev)]["abs_err_s"]
            means.append(float(sub.mean()) if len(sub) else float("nan"))
            stds.append(float(sub.std(ddof=1)) if len(sub) > 1 else 0.0)
        ax.bar(
            x + (i - 0.5) * width,
            means,
            width,
            yerr=stds,
            color=colors.get(method, "gray"),
            label=method,
            capsize=4,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(events)
    ax.set_ylabel("|Timing error| (s)", fontname="Arial", fontsize=14)
    ax.set_title(f"Fig-RiCTO-2  {rp.sub_label} vs GT 5 N window", fontname="Arial", fontsize=14)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 11})
    _setup_ax(ax)
    fig.tight_layout()
    out = manuscript_figures_dir() / rp.sub_label / "Fig-RiCTO-2.png"
    _save(fig, out, dpi=dpi)
    plt.close(fig)
    return out


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
        f"{fig_id}  {rp.sub_label}  {hand}  {section}",
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
| Fig-EHF-1..4 | `manuscript_figures.plot_ehf_resultant_rmse_panel` | EHF timeseries + RMSE_all_apps |
| Fig-L5S1-1 | `manuscript_figures.plot_l5s1_force_panel` | L5S1 Force_Resultant |
| Fig-L5S1-2 | `manuscript_figures.plot_l5s1_peak_panel` | L5S1 peaks long table |

Style: Arial 14/11, `APP_PLOT_STYLE` (MeasuredEHF black dashed, HeavyHand red, preRiCTO darkorange, postRiCTO blue).
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
    args = ap.parse_args()
    print(process_subject(args.namecode))


if __name__ == "__main__":
    main()

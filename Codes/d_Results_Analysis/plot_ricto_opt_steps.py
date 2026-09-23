# -*- coding: utf-8 -*-
"""Poster figures: step-by-step RiCTO residual-fit optimization.

Default trial: SUB7 / 15kg_10bpm / 10AB.

Pedagogy (not residual × w):
  r(t) ≈ B (1 − w(t; θ)),  minimize SSE of [r − B(1 − w_smooth)].
Hand-force gating (Step 6 only): f = w · f_est.
"""

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
    analysis_asymmetric_root,
    parse_mass_kg,
    result_paths,
)
from optimization import ricto_config as ricto_cfg  # noqa: E402
from optimization.ricto_optimize import (  # noqa: E402
    _bounds_native,
    baseline_theory,
    detect_init_guess,
    reparam_to_theta,
    rectangle_weight_curve,
    residual_vector,
    smooth_weight_curve,
    smoothstep_ramp,
    sse_cost,
    theta_to_reparam,
)

POSTER_DPI = 300
COLOR_RESIDUAL = "0.2"
COLOR_B = "0.45"
COLOR_PRE = "darkorange"
COLOR_POST = "blue"
COLOR_INIT = "0.55"
COLOR_ERR_INIT = "#AA5500"
COLOR_ERR_OPT = "#1a7a3c"


def _setup_ax(ax) -> None:
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(direction="in", labelsize=11)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontname("Arial")


def _legend_just_above_force_zero(ax, *, fontsize: int = 10, y_n: float = 4.0):
    """Place legend just above Force = 0 N (data y), left side — avoids profile overlap."""
    from matplotlib.transforms import blended_transform_factory

    trans = blended_transform_factory(ax.transAxes, ax.transData)
    return ax.legend(
        frameon=False,
        prop={"family": "Arial", "size": fontsize},
        loc="lower left",
        bbox_to_anchor=(0.02, y_n),
        bbox_transform=trans,
        borderaxespad=0.0,
    )

def _save(fig, out_path: Path, dpi: int = POSTER_DPI) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    return out_path


def poster_out_dir(sub: str, condition: str, seg: str) -> Path:
    root = analysis_asymmetric_root() / "_figures" / "RiCTO_poster" / f"{sub}_{condition}_{seg}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def timeseries_path(sub: str, condition: str, seg: str) -> Path:
    return (
        analysis_asymmetric_root()
        / "RiCTO"
        / "TimeSeries"
        / sub
        / condition
        / f"{sub}_{condition}_{seg}_RiCTO_timeseries.csv"
    )


def load_all_summary_row(
    sub: str,
    condition: str,
    seg: str,
) -> Optional[pd.Series]:
    csv_path = analysis_asymmetric_root() / "RiCTO" / "_validation" / "all_summary.csv"
    if not csv_path.is_file():
        return None
    df = pd.read_csv(csv_path)
    mask = (
        (df["sub"].astype(str) == sub)
        & (df["condition"].astype(str) == condition)
        & (df["seg"].astype(str) == seg)
    )
    hit = df.loc[mask]
    if hit.empty:
        return None
    # Prefer least_squares when multiple solvers present
    ls = hit[hit["solver"].astype(str) == "least_squares"]
    return (ls if not ls.empty else hit).iloc[0]


def resolve_namecode(sub: str, condition: str, seg: str, row: Optional[pd.Series]) -> str:
    if row is not None and "namecode" in row.index and pd.notna(row["namecode"]):
        return str(row["namecode"])
    # Fallback: scan PATH_RULE subject map via ResultPaths-friendly codes is hard;
    # try common SUB7 mapping from validation.
    if sub == "SUB7":
        return "260526_PJH"
    raise ValueError(f"Cannot resolve namecode for {sub} {condition} {seg}")


def load_trial(
    sub: str,
    condition: str,
    seg: str,
) -> Dict:
    ts = timeseries_path(sub, condition, seg)
    if not ts.is_file():
        raise FileNotFoundError(ts)
    df = pd.read_csv(ts)
    t = df["time"].to_numpy(dtype=float)
    residual = df["residual"].to_numpy(dtype=float)
    w_smooth_csv = (
        df["w_smooth"].to_numpy(dtype=float) if "w_smooth" in df.columns else None
    )
    w_rect_csv = df["w_rect"].to_numpy(dtype=float) if "w_rect" in df.columns else None

    row = load_all_summary_row(sub, condition, seg)
    box_mass = float(row["box_mass_kg"]) if row is not None else float(parse_mass_kg(condition))
    B = float(baseline_theory(box_mass))

    if row is not None and all(k in row.index for k in ("t1", "d1", "t2", "d2")):
        theta_star = np.array(
            [float(row["t1"]), float(row["d1"]), float(row["t2"]), float(row["d2"])],
            dtype=float,
        )
    else:
        # Recover θ* loosely from w_smooth edges if summary missing
        theta_star = detect_init_guess(t, residual, B)

    w_smooth = smooth_weight_curve(t, *theta_star)
    w_rect = rectangle_weight_curve(t, *theta_star)
    if w_smooth_csv is not None:
        w_smooth = w_smooth_csv
    if w_rect_csv is not None:
        w_rect = w_rect_csv

    theta0 = detect_init_guess(t, residual, B)
    w0 = smooth_weight_curve(t, *theta0)
    sse0 = sse_cost(theta0, t, residual, B)
    sse_star = sse_cost(theta_star, t, residual, B)

    namecode = resolve_namecode(sub, condition, seg, row)
    return {
        "sub": sub,
        "condition": condition,
        "seg": seg,
        "namecode": namecode,
        "t": t,
        "residual": residual,
        "B": B,
        "box_mass": box_mass,
        "theta_star": theta_star,
        "theta0": theta0,
        "w_smooth": w_smooth,
        "w_rect": w_rect,
        "w0": w0,
        "sse0": sse0,
        "sse_star": sse_star,
        "row": row,
    }


def _title(ax, step: int, text: str) -> None:
    ax.set_title(f"Step {step}.  {text}", fontname="Arial", fontsize=13, loc="left", pad=8)


def _xlabel(ax) -> None:
    ax.set_xlabel("Time (s)", fontname="Arial", fontsize=12)


def _ylabel(ax, text: str) -> None:
    ax.set_ylabel(text, fontname="Arial", fontsize=12)


def _annotate_theta(ax, theta: Sequence[float], y: float = 1.08) -> None:
    t1, d1, t2, d2 = map(float, theta)
    ax.axvline(t1, color=COLOR_POST, ls=":", lw=1.0, alpha=0.8)
    ax.axvline(t1 + d1, color=COLOR_POST, ls=":", lw=1.0, alpha=0.5)
    ax.axvline(t2, color=COLOR_POST, ls=":", lw=1.0, alpha=0.8)
    ax.axvline(t2 + d2, color=COLOR_POST, ls=":", lw=1.0, alpha=0.5)
    ax.text(
        0.02,
        0.95,
        (
            rf"$\theta^*=(t_1={t1:.3f},\ d_1={d1:.3f},"
            "\n"
            rf"\quad t_2={t2:.3f},\ d_2={d2:.3f})$ s"
        ),
        transform=ax.transAxes,
        fontsize=9,
        va="top",
        ha="left",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="0.75", alpha=0.9),
    )


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def plot_step1(data: Dict, out_dir: Path, *, dpi: int = POSTER_DPI, ax=None):
    import matplotlib.pyplot as plt

    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(8.5, 3.8), dpi=dpi)
    else:
        fig = ax.figure

    t, r, B = data["t"], data["residual"], data["B"]
    ax.plot(t, r, color=COLOR_RESIDUAL, lw=2.0, label=r"Observed residual $r(t)$")
    ax.axhline(B, color=COLOR_B, ls="--", lw=1.5, label=rf"Baseline $B = m_{{\mathrm{{box}}}}|g|$ ({B:.1f} N)")
    ax.axhline(0.0, color="0.7", ls="-", lw=0.8)
    _title(ax, 1, "Observed pelvis residual (HeavyHand)")
    _ylabel(ax, "Pelvis residual (N)")
    _xlabel(ax)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 10})
    _setup_ax(ax)
    if own:
        fig.tight_layout()
        return _save(fig, out_dir / "Step1_observed_residual.png", dpi=dpi), fig
    return None, fig


def plot_step2(data: Dict, out_dir: Path, *, dpi: int = POSTER_DPI, ax=None):
    import matplotlib.pyplot as plt

    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(8.5, 3.8), dpi=dpi)
    else:
        fig = ax.figure

    t = data["t"]
    ax.plot(t, 100.0 * data["w_rect"], color=COLOR_PRE, lw=2.2, label=r"$w_{\mathrm{rect}}$ (preRiCTO)")
    ax.plot(t, 100.0 * data["w_smooth"], color=COLOR_POST, lw=2.2, label=r"$w_{\mathrm{smooth}}$ (postRiCTO)")
    _annotate_theta(ax, data["theta_star"])
    ax.set_ylim(-5, 118)
    _title(ax, 2, "Contact weight families $w(t;\\theta)$")
    _ylabel(ax, "Load transfer (%)")
    _xlabel(ax)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 10}, loc="center right")
    _setup_ax(ax)
    if own:
        fig.tight_layout()
        return _save(fig, out_dir / "Step2_weight_families.png", dpi=dpi), fig
    return None, fig


def plot_step3(data: Dict, out_dir: Path, *, dpi: int = POSTER_DPI, ax=None):
    import matplotlib.pyplot as plt

    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(8.5, 3.8), dpi=dpi)
    else:
        fig = ax.figure

    t, r, B = data["t"], data["residual"], data["B"]
    model_rect = B * (1.0 - data["w_rect"])
    model_smooth = B * (1.0 - data["w_smooth"])
    ax.plot(t, r, color=COLOR_RESIDUAL, lw=1.8, label=r"$r(t)$ observed")
    ax.plot(t, model_rect, color=COLOR_PRE, lw=1.8, label=r"$B(1-w_{\mathrm{rect}})$")
    ax.plot(t, model_smooth, color=COLOR_POST, lw=2.0, label=r"$B(1-w_{\mathrm{smooth}})$")
    ax.axhline(B, color=COLOR_B, ls="--", lw=1.0, alpha=0.7)
    ax.axhline(0.0, color="0.7", ls="-", lw=0.8)
    _title(ax, 3, r"Residual model: $r(t)\approx B(1-w)$")
    _ylabel(ax, "Force (N)")
    _xlabel(ax)
    _setup_ax(ax)
    _legend_just_above_force_zero(ax, fontsize=10)
    if own:
        fig.tight_layout()
        return _save(fig, out_dir / "Step3_model_B_one_minus_w.png", dpi=dpi), fig
    return None, fig


def plot_step4(data: Dict, out_dir: Path, *, dpi: int = POSTER_DPI, ax=None):
    import matplotlib.pyplot as plt

    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(8.5, 3.8), dpi=dpi)
    else:
        fig = ax.figure

    t, r, B = data["t"], data["residual"], data["B"]
    e0 = r - B * (1.0 - data["w0"])
    e_star = r - B * (1.0 - data["w_smooth"])
    ax.plot(t, e0, color=COLOR_ERR_INIT, lw=1.6, alpha=0.9, label=rf"init $\theta_0$: SSE={data['sse0']:.2e}")
    ax.plot(t, e_star, color=COLOR_ERR_OPT, lw=2.0, label=rf"opt $\theta^*$: SSE={data['sse_star']:.2e}")
    ax.axhline(0.0, color="0.7", ls="-", lw=0.8)
    ax.fill_between(t, e_star, 0.0, color=COLOR_ERR_OPT, alpha=0.12)
    _title(ax, 4, r"Fit error $e(t)=r-B(1-w_{\mathrm{smooth}})$ — init vs optimized")
    _ylabel(ax, "Error (N)")
    _xlabel(ax)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 10})
    _setup_ax(ax)
    if own:
        fig.tight_layout()
        return _save(fig, out_dir / "Step4_error_and_cost.png", dpi=dpi), fig
    return None, fig


def plot_step5(data: Dict, out_dir: Path, *, dpi: int = POSTER_DPI, ax=None):
    import matplotlib.pyplot as plt
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes

    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(8.5, 3.8), dpi=dpi)
    else:
        fig = ax.figure

    t = data["t"]
    t1, d1, t2, d2 = map(float, data["theta_star"])
    w_star = data["w_smooth"]
    ax.plot(t, 100.0 * w_star, color=COLOR_POST, lw=2.4, label=r"$w^*(t;\theta^*)$")
    ax.plot(t, 100.0 * data["w_rect"], color=COLOR_PRE, lw=1.4, alpha=0.7, label=r"$w_{\mathrm{rect}}$ (same $\theta^*$)")
    _annotate_theta(ax, data["theta_star"])
    ax.set_ylim(-5, 118)
    # Zoom x around contact
    t_lo = max(float(t[0]), t1 - 0.4)
    t_hi = min(float(t[-1]), t2 + d2 + 0.4)
    ax.set_xlim(t_lo, t_hi)
    _title(ax, 5, r"Optimized load-transfer schedule $w^*(t;\theta^*)$")
    _ylabel(ax, "Load transfer (%)")
    _xlabel(ax)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 10}, loc="upper right")
    _setup_ax(ax)

    # Inset: smoothstep decomposition
    if own:
        axins = inset_axes(ax, width="38%", height="42%", loc="center left", borderpad=1.5)
        s_up = smoothstep_ramp(t, t1, d1)
        s_dn = smoothstep_ramp(t, t2, d2)
        axins.plot(t, s_up, color="#4C78A8", lw=1.3, label=r"$s(t;t_1,d_1)$")
        axins.plot(t, s_dn, color="#F58518", lw=1.3, label=r"$s(t;t_2,d_2)$")
        axins.plot(t, np.clip(s_up - s_dn, 0, 1), color=COLOR_POST, lw=1.6, label=r"$w^*$")
        axins.set_xlim(t_lo, t_hi)
        axins.set_ylim(-0.05, 1.15)
        axins.set_title("smoothstep build", fontname="Arial", fontsize=8)
        axins.tick_params(labelsize=7)
        axins.legend(frameon=False, fontsize=6, loc="upper right")
        for spine in ("top", "right"):
            axins.spines[spine].set_visible(False)

    if own:
        # Avoid tight_layout with inset_axes (incompatible warning)
        fig.subplots_adjust(left=0.10, right=0.98, bottom=0.14, top=0.88)
        return _save(fig, out_dir / "Step5_optimized_w_star.png", dpi=dpi), fig
    return None, fig


def plot_step6(data: Dict, out_dir: Path, *, dpi: int = POSTER_DPI, ax=None):
    import matplotlib.pyplot as plt
    import PATH_RULE as _path
    from optimization.ricto_io import read_opensim_storage

    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(8.5, 3.8), dpi=dpi)
    else:
        fig = ax.figure

    namecode = data["namecode"]
    cond, seg = data["condition"], data["seg"]
    cp = _path.ResultPaths(namecode).for_condition(cond)
    plotted = False
    for app in ("MeasuredEHF", "preRiCTO", "postRiCTO"):
        try:
            mot = cp.extload_path(seg, app)
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
            ax.plot(
                mdf["time"].to_numpy(dtype=float),
                mdf[hand_col].to_numpy(dtype=float),
                color=sty["color"],
                linestyle=sty["linestyle"],
                lw=1.6 if lab == "L" else 1.0,
                alpha=0.95 if lab == "L" else 0.5,
                label=f"{sty['label']} {lab}",
            )
            plotted = True
    if not plotted:
        ax.text(0.5, 0.5, "ExtLoad MOT not available", ha="center", va="center", transform=ax.transAxes)
    _title(ax, 6, r"Hand-force gating: $f = w\cdot f_{\mathrm{est}}$ (MeasuredEHF = GT)")
    _ylabel(ax, "Hand Fy (N)")
    _xlabel(ax)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 9}, ncol=2)
    _setup_ax(ax)
    if own:
        fig.tight_layout()
        return _save(fig, out_dir / "Step6_hand_force_gating.png", dpi=dpi), fig
    return None, fig


def plot_strip(data: Dict, out_dir: Path, *, dpi: int = POSTER_DPI) -> Path:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(16, 8.5), dpi=dpi)
    flat = axes.ravel()
    plotters = (
        plot_step1,
        plot_step2,
        plot_step3,
        plot_step4,
        plot_step5,
        plot_step6,
    )
    for ax, fn in zip(flat, plotters):
        fn(data, out_dir, dpi=dpi, ax=ax)

    # Strip step5: add compact theta text only (no inset on shared grid)
    # Step titles already set by each plotter.
    sub, cond, seg = data["sub"], data["condition"], data["seg"]
    fig.suptitle(
        f"RiCTO optimization steps — {sub}  {cond}  {seg}",
        fontname="Arial",
        fontsize=15,
        y=0.995,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = _save(fig, out_dir / "Strip_all_steps.png", dpi=dpi)
    plt.close(fig)
    return out


def generate_all(
    sub: str = "SUB7",
    condition: str = "15kg_10bpm",
    seg: str = "10AB",
    *,
    dpi: int = POSTER_DPI,
) -> Dict[str, Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = load_trial(sub, condition, seg)
    out_dir = poster_out_dir(sub, condition, seg)
    paths: Dict[str, Path] = {}

    for key, fn in (
        ("Step1", plot_step1),
        ("Step2", plot_step2),
        ("Step3", plot_step3),
        ("Step4", plot_step4),
        ("Step5", plot_step5),
        ("Step6", plot_step6),
    ):
        path, fig = fn(data, out_dir, dpi=dpi)
        if fig is not None:
            plt.close(fig)
        if path is not None:
            paths[key] = path

    paths["Strip"] = plot_strip(data, out_dir, dpi=dpi)
    return paths


def trace_least_squares(
    time_s: np.ndarray,
    residual: np.ndarray,
    baseline: float,
    x0: Sequence[float],
) -> Tuple[List[np.ndarray], List[float], Dict]:
    """Replay default RiCTO nonlinear LS; record every residual-vector eval.

    Returns (theta_history, sse_history, solver_info).
    First entry is the clipped reparam start u0 → θ; last matches solver result.
    """
    from scipy.optimize import least_squares

    t = np.asarray(time_s, float)
    r = np.asarray(residual, float)
    t0, t_end = float(t[0]), float(t[-1])
    b = _bounds_native(t0, t_end)
    u0 = theta_to_reparam(x0)
    u0[0] = np.clip(u0[0], *b["t1"])
    u0[1] = np.clip(u0[1], *b["d"])
    u0[2] = np.clip(u0[2], *b["delta"])
    u0[3] = np.clip(u0[3], *b["d"])
    lo = np.array([b["t1"][0], b["d"][0], b["delta"][0], b["d"][0]])
    hi = np.array([b["t1"][1], b["d"][1], b["delta"][1], b["d"][1]])

    thetas: List[np.ndarray] = []
    sses: List[float] = []

    def _record(u: np.ndarray) -> np.ndarray:
        th = reparam_to_theta(u)
        e = residual_vector(th, t, r, baseline)
        thetas.append(np.asarray(th, float).copy())
        sses.append(float(np.sum(np.asarray(e, float) ** 2)))
        return e

    # Explicit start frame (before Jacobian / TRF probing)
    _record(u0)

    def fun(u):
        return _record(u)

    res = least_squares(
        fun,
        u0,
        bounds=(lo, hi),
        loss=ricto_cfg.LS_LOSS,
        max_nfev=8000,
    )
    th_final = reparam_to_theta(res.x)
    # Ensure final θ* is last frame even if last eval differed slightly
    thetas.append(np.asarray(th_final, float).copy())
    sses.append(sse_cost(th_final, t, r, baseline))

    info = {
        "success": bool(res.success),
        "nfev": int(res.nfev),
        "message": str(res.message),
        "cost": float(sses[-1]),
        "params": th_final,
        "x0": np.asarray(x0, float),
        "n_recorded": len(thetas),
    }
    return thetas, sses, info


def _subsample_trace(
    thetas: Sequence[np.ndarray],
    sses: Sequence[float],
    *,
    max_frames: int = 40,
) -> Tuple[List[np.ndarray], List[float], List[int]]:
    """Keep first/last; prefer cost-improving evals; pad with evenly spaced."""
    n = len(thetas)
    if n == 0:
        return [], [], []
    improve = [0]
    best = sses[0]
    for i in range(1, n):
        if sses[i] < best - 1e-6:
            improve.append(i)
            best = sses[i]
    if improve[-1] != n - 1:
        improve.append(n - 1)

    if len(improve) >= max_frames:
        idx = np.unique(
            np.round(np.linspace(0, len(improve) - 1, max_frames)).astype(int)
        )
        keep = [improve[i] for i in idx]
    else:
        keep = list(improve)
        # Fill with evenly spaced evals so GIF is not too short
        need = max_frames - len(keep)
        extra = [
            int(i)
            for i in np.linspace(0, n - 1, need + 2)[1:-1]
            if int(i) not in keep
        ]
        keep = sorted(set(keep + extra))[:max_frames]
        if keep[-1] != n - 1:
            keep.append(n - 1)

    return [thetas[i] for i in keep], [sses[i] for i in keep], keep


def make_opt_progress_gif(
    sub: str = "SUB7",
    condition: str = "15kg_10bpm",
    seg: str = "10AB",
    *,
    dpi: int = 120,
    fps: float = 4.0,
    max_frames: int = 40,
) -> Path:
    """Stacked Step3 (model) + Step4 (error) animated over LS θ path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter

    data = load_trial(sub, condition, seg)
    out_dir = poster_out_dir(sub, condition, seg)
    t = data["t"]
    r = data["residual"]
    B = data["B"]
    x0 = data["theta0"]

    thetas, sses, info = trace_least_squares(t, r, B, x0)
    th_f, sse_f, eval_idx = _subsample_trace(thetas, sses, max_frames=max_frames)
    n_frames = len(th_f)
    if n_frames < 2:
        raise RuntimeError("LS trace too short for GIF")

    # Fixed y-limits from init vs final extremes
    w0 = smooth_weight_curve(t, *x0)
    e0 = r - B * (1.0 - w0)
    w_last = smooth_weight_curve(t, *th_f[-1])
    e_last = r - B * (1.0 - w_last)
    y_model = (
        min(float(np.min(r)), float(np.min(B * (1.0 - w0))), -30.0) - 10,
        max(float(np.max(r)), float(B) + 30),
    )
    y_err = (
        min(float(np.min(e0)), float(np.min(e_last))) - 10,
        max(float(np.max(e0)), float(np.max(e_last))) + 10,
    )

    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(9.0, 7.2), dpi=dpi, sharex=True)
    fig.subplots_adjust(hspace=0.28, left=0.10, right=0.98, top=0.90, bottom=0.08)

    (line_r,) = ax0.plot(t, r, color=COLOR_RESIDUAL, lw=1.6, label=r"$r(t)$ observed", zorder=2)
    # Fixed init model (mustard) for reference; animated current model in blue
    ax0.plot(
        t,
        B * (1.0 - w0),
        color=COLOR_ERR_INIT,
        lw=1.5,
        alpha=0.85,
        label=r"$B(1-w)$ at $\theta_0$",
        zorder=2,
    )
    (line_model,) = ax0.plot(
        t,
        B * (1.0 - w0),
        color=COLOR_POST,
        lw=2.2,
        label=r"$B(1-w)$ current $\theta$",
        zorder=3,
    )
    ax0.axhline(B, color=COLOR_B, ls="--", lw=1.0, alpha=0.7)
    ax0.axhline(0.0, color="0.7", ls="-", lw=0.8)
    ax0.set_ylim(*y_model)
    ax0.set_ylabel("Force (N)", fontname="Arial", fontsize=12)
    ax0.set_title("Step 3. Residual model", fontname="Arial", fontsize=12, loc="left")
    _setup_ax(ax0)
    _legend_just_above_force_zero(ax0, fontsize=9)

    # Fixed init error (mustard) stays for the whole GIF — same cue as static Step 4
    ax1.plot(
        t,
        e0,
        color=COLOR_ERR_INIT,
        lw=1.6,
        alpha=0.9,
        label=rf"init $\theta_0$: SSE={float(sses[0]):.2e}",
        zorder=2,
    )
    (line_e,) = ax1.plot(
        t,
        e0,
        color=COLOR_ERR_OPT,
        lw=2.0,
        label="current $\\theta$",
        zorder=3,
    )
    fill = ax1.fill_between(t, e0, 0.0, color=COLOR_ERR_OPT, alpha=0.12)
    ax1.axhline(0.0, color="0.7", ls="-", lw=0.8)
    ax1.set_ylim(*y_err)
    ax1.set_ylabel("Error (N)", fontname="Arial", fontsize=12)
    ax1.set_xlabel("Time (s)", fontname="Arial", fontsize=12)
    ax1.set_title("Step 4. Fit error — init (mustard) held fixed", fontname="Arial", fontsize=12, loc="left")
    ax1.legend(frameon=False, prop={"family": "Arial", "size": 9}, loc="upper right")
    _setup_ax(ax1)

    sse0 = float(sses[0])
    sse_star = float(sses[-1])
    status = fig.text(
        0.01,
        0.97,
        "",
        fontname="Arial",
        fontsize=10,
        va="top",
        ha="left",
        family="monospace",
    )
    fig.suptitle(
        f"RiCTO nonlinear LS  —  {sub}  {condition}  {seg}",
        fontname="Arial",
        fontsize=13,
        y=0.995,
    )

    def _update(frame: int):
        nonlocal fill
        th = th_f[frame]
        w = smooth_weight_curve(t, *th)
        model = B * (1.0 - w)
        e = r - model
        line_model.set_ydata(model)
        line_e.set_ydata(e)
        line_e.set_label(rf"current $\theta$: SSE={sse_f[frame]:.2e}")
        fill.remove()
        fill = ax1.fill_between(t, e, 0.0, color=COLOR_ERR_OPT, alpha=0.12, zorder=1)
        ax1.legend(frameon=False, prop={"family": "Arial", "size": 9}, loc="upper right")
        t1, d1, t2, d2 = map(float, th)
        status.set_text(
            f"eval {frame + 1}/{n_frames}  (nfev={info['nfev']})   "
            f"SSE={sse_f[frame]:.3e}  (init {sse0:.3e} → * {sse_star:.3e})\n"
            f"θ=({t1:.3f}, {d1:.3f}, {t2:.3f}, {d2:.3f}) s"
        )
        return line_model, line_e, status

    anim = FuncAnimation(fig, _update, frames=n_frames, interval=1000.0 / fps, blit=False)
    out = out_dir / "OptProgress_Step3_Step4.gif"
    # Hold last frame ~1.5× longer via fps + PillowWriter; duplicate last frames
    writer = PillowWriter(fps=fps)
    anim.save(str(out), writer=writer)
    plt.close(fig)

    # Append quiet note file for poster captions
    meta = out_dir / "OptProgress_meta.txt"
    meta.write_text(
        (
            f"sub={sub} condition={condition} seg={seg}\n"
            f"init: detect_init_guess  CONTACT_FRAC={ricto_cfg.CONTACT_FRAC_OF_B}  "
            f"INIT_D={ricto_cfg.INIT_D}\n"
            f"theta0={np.asarray(x0, float).tolist()}\n"
            f"theta*={np.asarray(info['params'], float).tolist()}\n"
            f"SSE0={sse0:.6e}  SSE*={sse_star:.6e}\n"
            f"nfev={info['nfev']}  recorded={info['n_recorded']}  gif_frames={n_frames}\n"
            f"message={info['message']}\n"
        ),
        encoding="utf-8",
    )
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="RiCTO poster step figures")
    ap.add_argument("--sub", default="SUB7")
    ap.add_argument("--condition", default="15kg_10bpm")
    ap.add_argument("--seg", default="10AB")
    ap.add_argument("--dpi", type=int, default=POSTER_DPI)
    ap.add_argument("--gif", action="store_true", help="Also write LS progress GIF (Step3+4)")
    ap.add_argument("--gif-only", action="store_true", help="Only write the LS progress GIF")
    ap.add_argument("--gif-fps", type=float, default=4.0)
    ap.add_argument("--gif-frames", type=int, default=40)
    args = ap.parse_args(argv)

    paths: Dict[str, Path] = {}
    if not args.gif_only:
        paths.update(generate_all(args.sub, args.condition, args.seg, dpi=args.dpi))
    if args.gif or args.gif_only:
        paths["GIF"] = make_opt_progress_gif(
            args.sub,
            args.condition,
            args.seg,
            fps=args.gif_fps,
            max_frames=args.gif_frames,
        )
    for k, p in paths.items():
        print(f"{k}: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

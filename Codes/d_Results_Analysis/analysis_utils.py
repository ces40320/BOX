# -*- coding: utf-8 -*-
"""Shared helpers for Asymmetric results analysis (EHF / L5S1 / Residual).

Schema: Codes/d_Results_Analysis/STRUCTURE.md
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

_CODES = Path(__file__).resolve().parents[1]
_RUN_TOOLS = _CODES / "c_Run_Tools"
_HERE = Path(__file__).resolve().parent
for _p in (str(_CODES), str(_RUN_TOOLS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import PATH_RULE as _path  # noqa: E402
import SUB_Info as _sub_info  # noqa: E402
import config_methods as _cfg  # noqa: E402
from optimization.ricto_io import read_opensim_storage  # noqa: E402
from optimization.run_ricto import box_mass_from_condition  # noqa: E402

N_RESAMPLE = 101
FY_THRESH_N = 5.0
MIN_CONTACT_DUR_S = 0.30
RMSE_QUARTILES = ((0, 25), (25, 50), (50, 75), (75, 101))

EHF_APPS = ("MeasuredEHF", "HeavyHand", "preRiCTO", "postRiCTO")
EHF_AXES = ("ML", "Vertical", "AP", "Resultant")
L5S1_FORCE_AXES = (
    "Force_AP",
    "Force_Vertical",
    "Force_ML",
    "Force_Resultant",
)
L5S1_MOMENT_AXES = (
    "Moment_LateralBending",
    "Moment_AxialRotation",
    "Moment_FlexionExtension",
)
RESIDUAL_AXES = ("Fx", "Fy", "Fz")
RESIDUAL_COLS = {
    "Fx": "residual_pelvis_tx",
    "Fy": "residual_pelvis_ty",
    "Fz": "residual_pelvis_tz",
}

L5S1_FORCE_COLS = {
    "Force_AP": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fx",
    "Force_Vertical": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fy",
    "Force_ML": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fz",
}
L5S1_MOMENT_COLS = {
    "Moment_LateralBending": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_mx",
    "Moment_AxialRotation": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_my",
    "Moment_FlexionExtension": "L5_S1_IVDjnt_on_lumbar5_in_lumbar5_mz",
}

APP_PLOT_STYLE = {
    "MeasuredEHF": {"color": "black", "linestyle": "--", "label": "MeasuredEHF"},
    "HeavyHand": {"color": "red", "linestyle": "-", "label": "HeavyHand"},
    "preRiCTO": {"color": "darkorange", "linestyle": "-", "label": "preRiCTO"},
    "postRiCTO": {"color": "blue", "linestyle": "-", "label": "postRiCTO"},
    # Code key FreeBox; document-facing legend LoadShare (freebox_config.DISPLAY_NAME).
    "FreeBox": {"color": "seagreen", "linestyle": "-", "label": "LoadShare"},
}

# Preferred overlay order for single-segment EHF comparison (skip quietly if missing).
EHF_COMPARE_APPS = (
    "MeasuredEHF",
    "HeavyHand",
    "preRiCTO",
    "postRiCTO",
    "FreeBox",
)

P_COLS = [f"p{i:03d}" for i in range(N_RESAMPLE)]
SECTIONS = ("AB", "BC", "CA")


def analysis_asymmetric_root() -> Path:
    return Path(_path._ensure_dir(_path.ANALYSIS_DIR, "Asymmetric"))


def result_paths(namecode: str):
    return _path.ResultPaths(namecode)


def ensure_domain_dirs(domain: str, apps: Sequence[str], axes: Sequence[str]) -> None:
    root = analysis_asymmetric_root() / domain
    for app in apps:
        for ax in axes:
            (root / app / ax).mkdir(parents=True, exist_ok=True)
        (root / app / "_metrics").mkdir(parents=True, exist_ok=True)


def figures_dir(domain: str) -> Path:
    d = analysis_asymmetric_root() / "_figures" / domain
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_condition(cond: str) -> Tuple[float, int]:
    """Return (mass_kg, tempo_bpm)."""
    mass = float(box_mass_from_condition(cond))
    m = re.search(r"(\d+)\s*bpm", cond, flags=re.IGNORECASE)
    tempo = int(m.group(1)) if m else -1
    return mass, tempo


def parse_tempo_bpm(cond: str) -> int:
    return parse_condition(cond)[1]


def parse_mass_kg(cond: str) -> float:
    return parse_condition(cond)[0]


def section_of(seg: str) -> str:
    for _, prefix in _cfg.section_info("ABC"):
        if seg.endswith(prefix) and seg[: -len(prefix)].isdigit():
            return prefix
    raise ValueError(f"Cannot parse section from {seg!r}")


def list_segments(namecode: str, cond: str) -> List[str]:
    rp = result_paths(namecode)
    cp = rp.for_condition(cond)
    err = set(cp.error_log or [])
    return [s for s in cp.all_sections() if s not in err]


def load_storage(path: Union[str, Path]) -> pd.DataFrame:
    df, _ = read_opensim_storage(path)
    return df


def resolve_opensim_file(path: Union[str, Path]) -> Optional[Path]:
    """Prefer ``path`` under local ``OPENSIM_DIR``, else the Dropbox cowork twin."""
    local = Path(path)
    if local.is_file():
        return local
    try:
        rel = local.relative_to(Path(_path.OPENSIM_DIR))
    except ValueError:
        return None
    cowork = Path(_path.COWORK_OPENSIM_DIR) / rel
    if cowork.is_file():
        return cowork
    return None


def resolve_extload_mot(namecode: str, cond: str, seg: str, app: str) -> Optional[Path]:
    """Local ``OpenSim_Process`` first, then Dropbox ``COWORK_OPENSIM_DIR``."""
    cp = result_paths(namecode).for_condition(cond)
    return resolve_opensim_file(cp.extload_path(seg, app))


def contact_windows_fy(
    time_s: np.ndarray,
    fy_l: np.ndarray,
    fy_r: np.ndarray,
    *,
    thresh_n: float = FY_THRESH_N,
    min_dur_s: float = MIN_CONTACT_DUR_S,
) -> List[Tuple[float, float]]:
    t = np.asarray(time_s, dtype=float)
    total = np.abs(np.asarray(fy_l, dtype=float)) + np.abs(np.asarray(fy_r, dtype=float))
    contact = total >= float(thresh_n)
    if not np.any(contact):
        return []
    padded = np.concatenate([[False], contact, [False]])
    d = np.diff(padded.astype(int))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    wins: List[Tuple[float, float]] = []
    for s, e in zip(starts, ends):
        if e <= s:
            continue
        t_on = float(t[s])
        t_off = float(t[e - 1])
        if (t_off - t_on) >= float(min_dur_s):
            wins.append((t_on, t_off))
    return wins


def longest_window(wins: Sequence[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    if not wins:
        return None
    return max(wins, key=lambda w: w[1] - w[0])


def measured_contact_window(me_df: pd.DataFrame) -> Tuple[float, float]:
    win = longest_window(
        contact_windows_fy(
            me_df["time"].to_numpy(dtype=float),
            me_df["hand_force3_vy"].to_numpy(dtype=float),
            me_df["hand_force4_vy"].to_numpy(dtype=float),
        )
    )
    if win is None:
        t = me_df["time"].to_numpy(dtype=float)
        return float(t[0]), float(t[-1])
    return win


def crop_by_time(
    time_s: np.ndarray,
    values: Union[np.ndarray, Dict[str, np.ndarray]],
    t0: float,
    t1: float,
):
    """Crop 1D array or dict of arrays by time. Dict keeps a ``time`` key."""
    t = np.asarray(time_s, dtype=float)
    mask = (t >= t0) & (t <= t1)
    if not np.any(mask):
        i0 = int(np.argmin(np.abs(t - t0)))
        i1 = int(np.argmin(np.abs(t - t1)))
        if i1 < i0:
            i0, i1 = i1, i0
        mask = np.zeros_like(t, dtype=bool)
        mask[i0 : i1 + 1] = True
    if isinstance(values, dict):
        out = {k: np.asarray(v, dtype=float)[mask] for k, v in values.items()}
        out["time"] = t[mask]
        return out
    return t[mask], np.asarray(values, dtype=float)[mask]


def resample_series(values: np.ndarray, n: int = N_RESAMPLE) -> np.ndarray:
    y = np.asarray(values, dtype=float).ravel()
    if y.size == 0:
        return np.full(n, np.nan)
    if y.size == 1:
        return np.full(n, float(y[0]))
    x = np.linspace(0.0, 1.0, y.size)
    x_new = np.linspace(0.0, 1.0, n)
    kind = "cubic" if y.size >= 4 else "linear"
    try:
        f = interp1d(x, y, kind=kind, fill_value="extrapolate")
        return np.asarray(f(x_new), dtype=float)
    except Exception:
        f = interp1d(x, y, kind="linear", fill_value="extrapolate")
        return np.asarray(f(x_new), dtype=float)


def apply_ehf_report_signs(
    fx: np.ndarray, fy: np.ndarray, fz: np.ndarray, hand: str
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    fx = np.asarray(fx, dtype=float).copy()
    fy = np.asarray(fy, dtype=float).copy()
    fz = np.asarray(fz, dtype=float).copy()
    if hand.upper() == "L":
        fx = -fx
    fz = -fz
    return fx, fy, fz


def ehf_components_from_mot(df: pd.DataFrame, hand: str) -> Dict[str, np.ndarray]:
    """OpenSim MOT hand forces → report-frame ML/Vertical/AP/Resultant."""
    prefix = "hand_force3" if hand.upper() == "L" else "hand_force4"
    t = df["time"].to_numpy(dtype=float)
    fx = df[f"{prefix}_vx"].to_numpy(dtype=float)
    fy = df[f"{prefix}_vy"].to_numpy(dtype=float)
    fz = df[f"{prefix}_vz"].to_numpy(dtype=float)
    fx, fy, fz = apply_ehf_report_signs(fx, fy, fz, hand)
    return {
        "time": t,
        "ML": fx,
        "Vertical": fy,
        "AP": fz,
        "Resultant": np.sqrt(fx * fx + fy * fy + fz * fz),
    }


def scale_ratio_from_n_raw(n_raw: int) -> float:
    return float(N_RESAMPLE) / float(max(int(n_raw), 1))


def scale_ratio_row(
    *,
    cond: str,
    seg: str,
    onset_t: float,
    offset_t: float,
    n_raw: int,
) -> dict:
    duration_s = float(offset_t) - float(onset_t)
    mass, tempo = parse_condition(cond)
    return {
        "cond": cond,
        "section": section_of(seg),
        "seg": seg,
        "onset_t": float(onset_t),
        "offset_t": float(offset_t),
        "duration_s": duration_s,
        "n_raw": int(n_raw),
        "n_resampled": N_RESAMPLE,
        "scale_ratio": scale_ratio_from_n_raw(n_raw),
        "sec_per_pct": duration_s / 100.0 if duration_s > 0 else float("nan"),
        "tempo_bpm": tempo,
        "mass_kg": mass,
    }


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float).ravel()
    b = np.asarray(b, dtype=float).ravel()
    m = np.isfinite(a) & np.isfinite(b)
    if not np.any(m):
        return float("nan")
    d = a[m] - b[m]
    return float(np.sqrt(np.mean(d * d)))


def rmse_full_and_quartiles(meas: np.ndarray, pred: np.ndarray) -> Dict[str, float]:
    out = {"RMSE_full": rmse(meas, pred)}
    for i, (lo, hi) in enumerate(RMSE_QUARTILES, start=1):
        out[f"RMSE_q{i}"] = rmse(meas[lo:hi], pred[lo:hi])
    return out


def row_dict(cond: str, seg: str, series_101: np.ndarray) -> dict:
    d = {"cond": cond, "seg": seg}
    y = np.asarray(series_101, dtype=float).ravel()
    for i, col in enumerate(P_COLS):
        d[col] = float(y[i]) if i < y.size else float("nan")
    return d


def _cond_sort_key(cond: str) -> Tuple[float, int, str]:
    mass, tempo = parse_condition(cond)
    return (mass, tempo, cond)


def write_section_timeseries(
    path: Path,
    rows: List[dict],
    *,
    conds: Optional[Sequence[str]] = None,
) -> None:
    """Write/merge rows for one section file; replace overlapping conds."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["cond", "seg", *P_COLS])
    if path.is_file() and conds is not None:
        old = pd.read_csv(path)
        old = old[~old["cond"].isin(list(conds))]
        df = pd.concat([old, df_new], ignore_index=True)
    else:
        df = df_new
    if not df.empty:
        df["_ord"] = df["cond"].map(lambda c: _cond_sort_key(str(c)))
        df["_seg_n"] = df["seg"].astype(str).str.extract(r"^(\d+)", expand=False).astype(float)
        df = df.sort_values(["_ord", "_seg_n", "seg"]).drop(columns=["_ord", "_seg_n"])
    cols = ["cond", "seg", *P_COLS]
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    df[cols].to_csv(path, index=False)


def append_or_replace_subject_rows(
    path: Path,
    rows: List[dict],
    *,
    conds: Optional[Sequence[str]] = None,
) -> None:
    """Compatibility alias — prefer write_section_timeseries for section files."""
    write_section_timeseries(path, rows, conds=conds)


def merge_metric_csv(
    path: Path,
    rows: List[dict],
    *,
    conds: Sequence[str],
    sort_cols: Sequence[str],
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(rows)
    if path.is_file():
        old = pd.read_csv(path)
        old = old[~old["cond"].isin(list(conds))]
        df = pd.concat([old, df_new], ignore_index=True)
    else:
        df = df_new
    if not df.empty and sort_cols:
        df = df.sort_values(list(sort_cols)).reset_index(drop=True)
    df.to_csv(path, index=False)


def ground_and_hand_net_force(me_df: pd.DataFrame) -> np.ndarray:
    fx = (
        me_df["ground_force1_vx"].to_numpy(dtype=float)
        + me_df["ground_force2_vx"].to_numpy(dtype=float)
        + me_df["hand_force3_vx"].to_numpy(dtype=float)
        + me_df["hand_force4_vx"].to_numpy(dtype=float)
    )
    fy = (
        me_df["ground_force1_vy"].to_numpy(dtype=float)
        + me_df["ground_force2_vy"].to_numpy(dtype=float)
        + me_df["hand_force3_vy"].to_numpy(dtype=float)
        + me_df["hand_force4_vy"].to_numpy(dtype=float)
    )
    fz = (
        me_df["ground_force1_vz"].to_numpy(dtype=float)
        + me_df["ground_force2_vz"].to_numpy(dtype=float)
        + me_df["hand_force3_vz"].to_numpy(dtype=float)
        + me_df["hand_force4_vz"].to_numpy(dtype=float)
    )
    return np.sqrt(fx * fx + fy * fy + fz * fz)


def hicks_from_net(net: np.ndarray) -> dict:
    net = np.asarray(net, dtype=float)
    net = net[np.isfinite(net)]
    if net.size == 0:
        return {
            "net_max": float("nan"),
            "net_rms": float("nan"),
            "hicks_5pct_max": float("nan"),
            "hicks_5pct_rms": float("nan"),
            "hicks_1pct_max": float("nan"),
        }
    net_max = float(np.max(net))
    net_rms = float(np.sqrt(np.mean(net * net)))
    return {
        "net_max": net_max,
        "net_rms": net_rms,
        "hicks_5pct_max": 0.05 * net_max,
        "hicks_5pct_rms": 0.05 * net_rms,
        "hicks_1pct_max": 0.01 * net_max,
    }


def mean_std_plot(
    series_by_app: Dict[str, np.ndarray],
    *,
    title: str,
    ylabel: str,
    out_path: Union[str, Path],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 7), dpi=150)
    x = np.linspace(0, 100, N_RESAMPLE)
    for app, arr in series_by_app.items():
        a = np.asarray(arr, dtype=float)
        if a.ndim == 1:
            a = a[None, :]
        if a.size == 0 or not np.any(np.isfinite(a)):
            continue
        mean = np.nanmean(a, axis=0)
        std = np.nanstd(a, axis=0)
        sty = APP_PLOT_STYLE.get(app, {"color": "gray", "linestyle": "-", "label": app})
        ax.plot(
            x,
            mean,
            color=sty["color"],
            linestyle=sty["linestyle"],
            linewidth=2.0,
            label=sty["label"],
        )
        ax.fill_between(x, mean - std, mean + std, color=sty["color"], alpha=0.15)
    ax.set_xlabel("Time (%)", fontname="Arial", fontsize=14)
    ax.set_ylabel(ylabel, fontname="Arial", fontsize=14)
    ax.set_title(title, fontname="Arial", fontsize=14)
    ax.legend(frameon=False, prop={"family": "Arial", "size": 11})
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(direction="in")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def rows_to_matrix(rows: List[dict]) -> np.ndarray:
    if not rows:
        return np.zeros((0, N_RESAMPLE))
    return np.vstack([np.array([r[c] for c in P_COLS], dtype=float) for r in rows])

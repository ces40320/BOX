"""Chest wrap path anomaly detection, severity tiers, and SO gap-fill helpers.

Shared by ``wrap_gapfill/`` (detect, gap-fill), ``wrap_fbp/`` (trial l(q)
model) and ``RUN_fix_muscle_path_wrap_fail.py``.

Does not modify the shared scaled ``.osim``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Sequence

import numpy as np
import pandas as pd

CHEST_WRAP_NAMES = ("Chest_r", "Chest_l")

DEFAULT_DL_ABS_M = 0.015
DEFAULT_DL_REL = 0.08
# Path length within this factor of the end-point chord ⇒ wrap not engaged.
DEFAULT_PIERCE_LEN_FACTOR = 1.025
DEFAULT_PAD_S = 0.01

TIER_A_MAX_ISLAND_S = 0.05
TIER_A_TOTAL_BAD_S = 0.10
TIER_A_BAD_FRAC = 0.05
TIER_A_MAX_ISLANDS = 3
TIER_A_MAX_MUSCLES_SIMUL = 2
TIER_C_BAD_FRAC = 0.25

# Torso wrap local: posterior is -X (OpenSim LFB torso). Used only by Tier B2.
POSTERIOR_AXIS = 0
POSTERIOR_SIGN = -1.0


@dataclass
class Severity:
    trial_t0: float
    trial_t1: float
    trial_dur_s: float
    bad_frac: float
    n_islands: int
    max_island_s: float
    total_bad_s: float
    max_muscles_simul: int
    n_muscles_ever: int
    muscles_ever: list[str] = field(default_factory=list)
    islands: list[list[float]] = field(default_factory=list)


@dataclass
class DetectResult:
    namecode: str
    condition: str
    segment: str
    app: str
    model_path: str
    ik_path: str
    tier: str
    tier_reason: str
    severity: Severity
    frame_flags: list[dict[str, Any]] = field(default_factory=list)
    chest_muscles: list[str] = field(default_factory=list)
    error: str = ""


def maybe_add_opensim_dll() -> None:
    add_dll = getattr(os, "add_dll_directory", None)
    if add_dll is None:
        return
    dll_dir = "C:/OpenSim 4.5/bin"
    if os.path.isdir(dll_dir):
        add_dll(dll_dir)


def import_opensim():
    maybe_add_opensim_dll()
    import opensim as osim

    try:
        osim.Logger.setLevelString("error")
    except Exception:  # noqa: BLE001
        pass
    return osim


def repair_dir(namecode: str, approach: str) -> str:
    """Report dir ``Analysis/<protocol>/_diagnosis/<approach>/<SUB#>``.

    Never write tools or reports into ``OpenSim_Process/.../SUB#/`` or
    under ``Codes/``.
    """
    from PATH_RULE import ResultPaths, diagnosis_dir

    rp = ResultPaths(namecode)
    return diagnosis_dir(rp.protocol, approach, rp.sub_label)


# Path-length change in one IK frame that counts as a wrap side swap.
JUMP_DL_M = 0.05


def detect_length_jumps(
    osim,
    model_path: str,
    ik_path: str,
    *,
    muscles: Sequence[str] | None = None,
    dl_m: float = JUMP_DL_M,
    pad_s: float = DEFAULT_PAD_S,
) -> tuple[list[list[float]], list[str]]:
    """Short mid-trial path-length jumps (Chest wrap side swaps) from IK.

    A jump of ``>= dl_m`` that later returns (opposite sign, ``>= 50 %``
    magnitude) marks one island; islands are padded by ``pad_s`` and merged.
    ``muscles`` defaults to every Chest-wrapped muscle. Chronic straight
    paths (never jump) are ignored.

    Returns ``(islands, muscles_with_jumps)``.
    """
    from optimization.ricto_io import read_opensim_storage

    model = osim.Model(model_path)
    state = model.initSystem()
    names = list(muscles) if muscles else list_chest_path_muscles(model)
    ik_df, meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    indeg = _ik_in_degrees(meta)
    times = ik_df[tcol].to_numpy(dtype=float)
    objs = {m: model.getMuscles().get(m) for m in names}
    lengths = {m: np.full(len(times), np.nan) for m in names}
    for fi, (_, row) in enumerate(ik_df.iterrows()):
        _apply_ik_row(osim, model, state, row, indeg)
        for m, mus in objs.items():
            lengths[m][fi] = float(mus.getGeometryPath().getLength(state))

    raw: list[list[float]] = []
    jumped: list[str] = []
    n = len(times)
    for m in names:
        a = lengths[m]
        d = np.diff(a)
        jump = np.zeros(n, dtype=bool)
        jump[1:] = np.isfinite(d) & (np.abs(d) >= dl_m)
        if jump.any():
            jumped.append(m)
        i = 1
        while i < n:
            if not jump[i]:
                i += 1
                continue
            sign = float(a[i] - a[i - 1])
            j = i + 1
            while j < n:
                if jump[j]:
                    dj = float(a[j] - a[j - 1])
                    if sign * dj < 0 and abs(dj) >= 0.5 * abs(sign):
                        break
                j += 1
            end = j - 1 if j < n else n - 1
            raw.append([float(times[i]) - pad_s, float(times[end]) + pad_s])
            i = j + 1 if j < n else n
    raw.sort()
    merged: list[list[float]] = []
    for lo, hi in raw:
        if merged and lo <= merged[-1][1] + 1e-9:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged, jumped


def list_chest_path_muscles(model) -> list[str]:
    """Muscles whose GeometryPath wraps Chest_r and/or Chest_l."""
    names: list[str] = []
    muscles = model.getMuscles()
    for i in range(muscles.getSize()):
        mus = muscles.get(i)
        try:
            wraps = mus.getGeometryPath().getWrapSet()
        except Exception:  # noqa: BLE001
            continue
        for j in range(wraps.getSize()):
            pw = wraps.get(j)
            try:
                wname = pw.getWrapObjectName()
            except Exception:  # noqa: BLE001
                try:
                    wname = str(pw.get_wrap_object())
                except Exception:  # noqa: BLE001
                    continue
            if wname in CHEST_WRAP_NAMES:
                names.append(mus.getName())
                break
    return names


def _wrap_ellipsoid(osim, model, wrap_name: str):
    bodies = model.getBodySet()
    for bi in range(bodies.getSize()):
        body = bodies.get(bi)
        wset = body.getWrapObjectSet()
        for wi in range(wset.getSize()):
            w = wset.get(wi)
            if w.getName() != wrap_name:
                continue
            we = osim.WrapEllipsoid.safeDownCast(w)
            if we is None:
                return None
            return body, we
    return None


def _rotation_body_xyz(osim, rx: float, ry: float, rz: float):
    R = osim.Rotation()
    R.setRotationToBodyFixedXYZ(osim.Vec3(rx, ry, rz))
    return R


def _to_wrap_local(osim, state, body, wrap, p_ground: np.ndarray) -> np.ndarray:
    X_GB = body.getTransformInGround(state)
    p_body = X_GB.shiftBaseStationToFrame(osim.Vec3(
        float(p_ground[0]), float(p_ground[1]), float(p_ground[2])
    ))
    trans = wrap.get_translation()
    rot = wrap.get_xyz_body_rotation()
    R = _rotation_body_xyz(osim, rot.get(0), rot.get(1), rot.get(2))
    X_BW = osim.Transform(R, trans)
    p_w = X_BW.shiftBaseStationToFrame(p_body)
    return np.array([p_w.get(0), p_w.get(1), p_w.get(2)], dtype=float)


def _inside_ellipsoid(p: np.ndarray, radii) -> bool:
    a, b, c = float(radii.get(0)), float(radii.get(1)), float(radii.get(2))
    if min(a, b, c) <= 0:
        return False
    return (p[0] / a) ** 2 + (p[1] / b) ** 2 + (p[2] / c) ** 2 <= 1.0 + 1e-9


def _chord_hits_ellipsoid(p0: np.ndarray, p1: np.ndarray, radii, n: int = 21) -> bool:
    for s in np.linspace(0.05, 0.95, n):
        if _inside_ellipsoid((1.0 - s) * p0 + s * p1, radii):
            return True
    return False


def _ends_world(state, muscle) -> tuple[np.ndarray, np.ndarray] | None:
    pts = muscle.getGeometryPath().getPathPointSet()
    if pts.getSize() < 2:
        return None
    a = pts.get(0)
    b = pts.get(pts.getSize() - 1)
    try:
        la = a.getLocationInGround(state)
        lb = b.getLocationInGround(state)
    except Exception:  # noqa: BLE001
        return None
    return (
        np.array([la.get(0), la.get(1), la.get(2)], dtype=float),
        np.array([lb.get(0), lb.get(1), lb.get(2)], dtype=float),
    )


def _muscle_wrap_names(muscle) -> list[str]:
    out = []
    try:
        wset = muscle.getGeometryPath().getWrapSet()
    except Exception:  # noqa: BLE001
        return list(CHEST_WRAP_NAMES)
    for j in range(wset.getSize()):
        pw = wset.get(j)
        try:
            wn = pw.getWrapObjectName()
        except Exception:  # noqa: BLE001
            wn = str(pw.get_wrap_object())
        if wn in CHEST_WRAP_NAMES:
            out.append(wn)
    return out


def _apply_ik_row(osim, model, state, row: pd.Series, in_degrees: bool) -> None:
    coords = model.updCoordinateSet()
    for cname, val in row.items():
        if cname in ("time", "Time"):
            continue
        if not coords.contains(str(cname)):
            continue
        if not np.isfinite(val):
            continue
        coord = coords.get(str(cname))
        v = float(val)
        try:
            if in_degrees and coord.getMotionType() == osim.Coordinate.Rotational:
                v = float(np.deg2rad(v))
        except Exception:  # noqa: BLE001
            pass
        try:
            coord.setValue(state, v, False)
        except Exception:  # noqa: BLE001
            continue
    model.realizePosition(state)


def merge_intervals(
    times: np.ndarray,
    bad_mask: np.ndarray,
    *,
    pad_s: float,
    t0: float,
    t1: float,
) -> list[list[float]]:
    times = np.asarray(times, dtype=float)
    bad_mask = np.asarray(bad_mask, dtype=bool)
    if times.size == 0 or not bad_mask.any():
        return []
    raw: list[tuple[float, float]] = []
    i = 0
    n = len(times)
    while i < n:
        if not bad_mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and bad_mask[j + 1]:
            j += 1
        raw.append((float(times[i]), float(times[j])))
        i = j + 1
    merged: list[list[float]] = []
    for a, b in raw:
        a2, b2 = max(t0, a - pad_s), min(t1, b + pad_s)
        if not merged or a2 > merged[-1][1] + 1e-9:
            merged.append([a2, b2])
        else:
            merged[-1][1] = max(merged[-1][1], b2)
    return merged


def classify_tier(sev: Severity) -> tuple[str, str]:
    if sev.trial_dur_s <= 0:
        return "C", "empty_trial"
    if sev.bad_frac > TIER_C_BAD_FRAC:
        return "C", f"bad_frac={sev.bad_frac:.3f}>{TIER_C_BAD_FRAC}"
    if sev.n_islands == 0:
        return "A", "no_bad_frames"
    a_ok = (
        sev.max_island_s <= TIER_A_MAX_ISLAND_S
        and sev.total_bad_s <= TIER_A_TOTAL_BAD_S
        and sev.bad_frac <= TIER_A_BAD_FRAC
        and sev.n_islands <= TIER_A_MAX_ISLANDS
        and sev.max_muscles_simul <= TIER_A_MAX_MUSCLES_SIMUL
    )
    if a_ok:
        return "A", "short_sparse_ok"
    return (
        "B",
        (
            f"max_island={sev.max_island_s:.3f}s total_bad={sev.total_bad_s:.3f}s "
            f"islands={sev.n_islands} simul={sev.max_muscles_simul}"
        ),
    )


def good_intervals(t0: float, t1: float, bad: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    if t1 <= t0:
        return []
    if not bad:
        return [(float(t0), float(t1))]
    out: list[tuple[float, float]] = []
    cursor = float(t0)
    for pair in bad:
        a, b = float(pair[0]), float(pair[1])
        if a > cursor + 1e-9:
            out.append((cursor, min(a, float(t1))))
        cursor = max(cursor, b)
        if cursor >= t1:
            break
    if cursor < float(t1) - 1e-9:
        out.append((cursor, float(t1)))
    return [(a, b) for a, b in out if b - a > 1e-4]


def _ik_in_degrees(meta: dict) -> bool:
    for line in meta.get("header_lines", []) or []:
        if "indegrees" in str(line).lower():
            return "yes" in str(line).lower()
    return True


def scan_trial(
    *,
    osim,
    model_path: str,
    ik_path: str,
    namecode: str = "",
    condition: str = "",
    segment: str = "",
    app: str = "",
    pad_s: float = DEFAULT_PAD_S,
    dl_abs: float = DEFAULT_DL_ABS_M,
    dl_rel: float = DEFAULT_DL_REL,
    pierce_factor: float = DEFAULT_PIERCE_LEN_FACTOR,
    time_window: tuple[float, float] | None = None,
) -> DetectResult:
    """Scan IK poses. Flag Chest-wrap pierce / point-inside / length jumps."""
    from optimization.ricto_io import read_opensim_storage

    blank = DetectResult(
        namecode, condition, segment, app, model_path, ik_path,
        "C", "error", Severity(0, 0, 0, 0, 0, 0, 0, 0, 0),
    )
    if not os.path.isfile(model_path):
        blank.error = f"missing model: {model_path}"
        blank.tier_reason = "missing_model"
        return blank
    if not os.path.isfile(ik_path):
        blank.error = f"missing IK: {ik_path}"
        blank.tier_reason = "missing_ik"
        return blank

    model = osim.Model(model_path)
    state = model.initSystem()
    chest = list_chest_path_muscles(model)
    focus = [n for n in chest if n.startswith("LTpT_")] or list(chest)
    wraps = {wn: _wrap_ellipsoid(osim, model, wn) for wn in CHEST_WRAP_NAMES}

    ik_df, ik_meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    in_degrees = _ik_in_degrees(ik_meta)
    if time_window is not None:
        ik_df = ik_df[
            (ik_df[tcol] >= time_window[0] - 1e-9)
            & (ik_df[tcol] <= time_window[1] + 1e-9)
        ].reset_index(drop=True)
    if ik_df.empty:
        blank.tier_reason = "no_ik_frames"
        blank.chest_muscles = chest
        return blank

    times = ik_df[tcol].to_numpy(dtype=float)
    lengths = {m: np.full(len(times), np.nan) for m in chest}
    flags_at = {m: [[] for _ in range(len(times))] for m in chest}
    objs = {m: model.getMuscles().get(m) for m in chest}

    for fi, (_, row) in enumerate(ik_df.iterrows()):
        _apply_ik_row(osim, model, state, row, in_degrees)
        for mname, mus in objs.items():
            try:
                L = float(mus.getGeometryPath().getLength(state))
            except Exception:  # noqa: BLE001
                L = float("nan")
            lengths[mname][fi] = L
            ends = _ends_world(state, mus)
            if ends is None or not np.isfinite(L):
                if not np.isfinite(L):
                    flags_at[mname][fi].append("length_nan")
                continue
            eucl = float(np.linalg.norm(ends[1] - ends[0]))
            hit = False
            inside = False
            for wn in _muscle_wrap_names(mus):
                info = wraps.get(wn)
                if not info:
                    continue
                body, wrap = info
                radii = wrap.get_dimensions()
                p0 = _to_wrap_local(osim, state, body, wrap, ends[0])
                p1 = _to_wrap_local(osim, state, body, wrap, ends[1])
                if _inside_ellipsoid(p0, radii) or _inside_ellipsoid(p1, radii):
                    inside = True
                if _chord_hits_ellipsoid(p0, p1, radii):
                    hit = True
            if inside:
                flags_at[mname][fi].append("point_inside")
            if hit and eucl > 1e-6 and L <= pierce_factor * eucl:
                flags_at[mname][fi].append("pierce")

    frame_flags: list[dict[str, Any]] = []
    pierce_mask = np.zeros(len(times), dtype=bool)
    for mname in chest:
        series = lengths[mname]
        for fi, fl in enumerate(flags_at[mname]):
            if not fl:
                continue
            pierce_mask[fi] = True
            frame_flags.append({
                "time_s": float(times[fi]),
                "muscle": mname,
                "flag": "|".join(sorted(set(fl))),
                "path_length": float(series[fi]) if np.isfinite(series[fi]) else None,
            })
        if series.size < 2:
            continue
        dL = np.abs(np.diff(series))
        prev = series[:-1]
        rel = np.where(np.abs(prev) > 1e-6, dL / np.abs(prev), dL)
        bad = (dL >= dl_abs) | (rel >= dl_rel) | (~np.isfinite(series[1:]))
        for k in np.where(bad)[0]:
            pierce_mask[k + 1] = True
            frame_flags.append({
                "time_s": float(times[k + 1]),
                "muscle": mname,
                "flag": "length_jump",
                "path_length": None if not np.isfinite(series[k + 1]) else float(series[k + 1]),
                "dL": None if not np.isfinite(dL[k]) else float(dL[k]),
            })

    t0, t1 = float(times[0]), float(times[-1])
    islands = merge_intervals(times, pierce_mask, pad_s=pad_s, t0=t0, t1=t1)
    total_bad = float(sum(b - a for a, b in islands))
    dur = float(max(t1 - t0, 0.0))

    # Simultaneous LTpT (or focus) count per frame.
    simul = np.zeros(len(times), dtype=int)
    ever: set[str] = set()
    buckets: dict[int, set[str]] = {}
    for row in frame_flags:
        if row["muscle"] not in focus:
            continue
        ever.add(row["muscle"])
        # nearest time index
        fi = int(np.argmin(np.abs(times - float(row["time_s"]))))
        buckets.setdefault(fi, set()).add(row["muscle"])
    for fi, ms in buckets.items():
        simul[fi] = len(ms)

    sev = Severity(
        trial_t0=t0,
        trial_t1=t1,
        trial_dur_s=dur,
        bad_frac=(total_bad / dur) if dur > 1e-9 else (1.0 if total_bad else 0.0),
        n_islands=len(islands),
        max_island_s=float(max((b - a for a, b in islands), default=0.0)),
        total_bad_s=total_bad,
        max_muscles_simul=int(simul.max()) if simul.size else 0,
        n_muscles_ever=len(ever),
        muscles_ever=sorted(ever),
        islands=islands,
    )
    tier, reason = classify_tier(sev)
    frame_flags.sort(key=lambda r: (r["time_s"], r["muscle"], r["flag"]))
    return DetectResult(
        namecode=namecode,
        condition=condition,
        segment=segment,
        app=app,
        model_path=model_path,
        ik_path=ik_path,
        tier=tier,
        tier_reason=reason,
        severity=sev,
        frame_flags=frame_flags,
        chest_muscles=chest,
    )


def detect_result_to_dict(res: DetectResult) -> dict[str, Any]:
    d = asdict(res)
    return d


def write_json(path: str, payload: dict) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def cubic_gap_fill_series(
    t_front: float,
    y_front: np.ndarray,
    dy_front: np.ndarray,
    t_back: float,
    y_back: np.ndarray,
    dy_back: np.ndarray,
    t_query: np.ndarray,
) -> np.ndarray:
    """Hermite cubic between two endpoints, one column per channel."""
    t_query = np.asarray(t_query, dtype=float)
    if t_back <= t_front + 1e-12 or t_query.size == 0:
        return np.zeros((0, y_front.size))
    u = ((t_query - t_front) / (t_back - t_front))[:, None]
    h00 = 2 * u**3 - 3 * u**2 + 1
    h10 = u**3 - 2 * u**2 + u
    h01 = -2 * u**3 + 3 * u**2
    h11 = u**3 - u**2
    dt = t_back - t_front
    return (
        h00 * y_front[None, :]
        + h10 * (dt * dy_front[None, :])
        + h01 * y_back[None, :]
        + h11 * (dt * dy_back[None, :])
    )


def stitch_sto_cubic(segment_paths: Sequence[str], out_path: str) -> tuple[int, float, float]:
    """Concatenate SO storages; Hermite-fill time gaps between segments."""
    from optimization.ricto_io import read_opensim_storage, write_opensim_storage

    if not segment_paths:
        raise ValueError("no segment paths to stitch")
    dfs = []
    meta = None
    for p in segment_paths:
        df, m = read_opensim_storage(p)
        if meta is None:
            meta = m
        dfs.append(df)
    tcol = "time" if "time" in dfs[0].columns else "Time"
    cols = [c for c in dfs[0].columns if all(c in d.columns for d in dfs)]
    if tcol not in cols:
        raise ValueError("time column missing after align")
    dfs = [d[cols].copy() for d in dfs]

    def _dt(df: pd.DataFrame) -> float:
        t = df[tcol].to_numpy(dtype=float)
        d = np.diff(t)
        d = d[d > 1e-6]
        return float(np.median(d)) if len(d) else 0.01

    pieces = [dfs[0]]
    for i in range(len(dfs) - 1):
        front, back = dfs[i], dfs[i + 1]
        ft = float(front[tcol].iloc[-1])
        bt = float(back[tcol].iloc[0])
        if bt <= ft + 1e-9:
            pieces.append(back)
            continue
        data_cols = [c for c in cols if c != tcol]
        y0 = front[data_cols].iloc[-1].to_numpy(dtype=float)
        y1 = back[data_cols].iloc[0].to_numpy(dtype=float)
        if len(front) >= 2:
            dt_f = float(front[tcol].iloc[-1] - front[tcol].iloc[-2])
            dy0 = (y0 - front[data_cols].iloc[-2].to_numpy(dtype=float)) / max(dt_f, 1e-9)
        else:
            dy0 = np.zeros_like(y0)
        if len(back) >= 2:
            dt_b = float(back[tcol].iloc[1] - back[tcol].iloc[0])
            dy1 = (back[data_cols].iloc[1].to_numpy(dtype=float) - y1) / max(dt_b, 1e-9)
        else:
            dy1 = np.zeros_like(y1)
        dt = _dt(front)
        tq = []
        t = ft + dt
        while t < bt - 1e-9:
            tq.append(round(t + 1e-9, 4))
            t += dt
        if tq:
            Y = cubic_gap_fill_series(ft, y0, dy0, bt, y1, dy1, np.asarray(tq, dtype=float))
            gap = pd.DataFrame(Y, columns=data_cols)
            gap.insert(0, tcol, tq)
            pieces.append(gap)
        pieces.append(back)

    out = pd.concat(pieces, ignore_index=True)
    out = out.drop_duplicates(subset=[tcol], keep="first")
    out = out.sort_values(tcol).reset_index(drop=True)
    write_opensim_storage(out_path, out, meta)
    return len(out), float(out[tcol].iloc[0]), float(out[tcol].iloc[-1])


def stamped_payload(results: list[DetectResult], **extra: Any) -> dict:
    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n": len(results),
        "results": [detect_result_to_dict(r) for r in results],
        **extra,
    }

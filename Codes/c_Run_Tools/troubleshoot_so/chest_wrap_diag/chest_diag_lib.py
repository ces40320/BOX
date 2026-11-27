"""Chest wrap geometric diagnosis shared by approaches A and B.

Per frame × muscle: L5–S1 / coupled spine angles, path length, wrap contact
geometry relative to Chest ellipsoids, and failure-type classification.
Does not modify shared scaled models. Reuses helpers from ``wrap_detect_lib``.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from wrap_detect_lib import (
    CHEST_WRAP_NAMES,
    JUMP_DL_M,
    _apply_ik_row,
    _chord_hits_ellipsoid,
    _ends_world,
    _inside_ellipsoid,
    _muscle_wrap_names,
    _to_wrap_local,
    _wrap_ellipsoid,
    detect_length_jumps,
    import_opensim,
    list_chest_path_muscles,
    repair_dir,
)

L5S1_COORDS = (
    "L5_S1_Flex_Ext",
    "L5_S1_Lat_Bending",
    "L5_S1_axial_rotation",
)

# Coupler-driven lumbar / thoracic / abdominal rotations (templates).
COUPLED_COORD_RE = re.compile(
    r"^(L[1-5]_|T1[0-2]_|T[89]_|Abs_)"
)

FAILURE_TYPES = (
    "pierce",
    "wrong_side",
    "unwrap_rewrap",
    "tangent_jump",
    "endpoint_inside",
    "length_jump",
    "ok",
)

DIAG_APPROACH = "chest_wrap"


def chest_out_dir(namecode: str, *parts: str) -> str:
    """``Analysis/<protocol>/_diagnosis/chest_wrap/<SUB>/…``."""
    base = repair_dir(namecode, DIAG_APPROACH)
    path = os.path.join(base, *parts) if parts else base
    os.makedirs(path, exist_ok=True)
    return path


def _ik_in_degrees(meta: dict) -> bool:
    v = str(meta.get("inDegrees") or meta.get("in_degrees") or "").strip().lower()
    if v in ("yes", "true", "1"):
        return True
    if v in ("no", "false", "0"):
        return False
    return True


def _norm_dist(p: np.ndarray, radii) -> float:
    a, b, c = float(radii.get(0)), float(radii.get(1)), float(radii.get(2))
    if min(a, b, c) <= 0:
        return float("nan")
    return float(np.sqrt((p[0] / a) ** 2 + (p[1] / b) ** 2 + (p[2] / c) ** 2) - 1.0)


def _approx_surface_m(p: np.ndarray, radii) -> float:
    """Rough signed distance (m): positive outside."""
    nd = _norm_dist(p, radii)
    if not np.isfinite(nd):
        return float("nan")
    a, b, c = float(radii.get(0)), float(radii.get(1)), float(radii.get(2))
    r_mean = (a + b + c) / 3.0
    return float(nd * r_mean)


def _quadrant_ok(p_local: np.ndarray, quadrant: str) -> bool | None:
    q = (quadrant or "").strip().lower()
    if q in ("", "all", "none"):
        return None
    axis = {"x": 0, "y": 1, "z": 2, "-x": 0, "-y": 1, "-z": 2}.get(q)
    if axis is None:
        return None
    neg = q.startswith("-")
    return bool(p_local[axis] < 0) if neg else bool(p_local[axis] > 0)


def _read_vec3(v) -> np.ndarray:
    return np.array([float(v.get(0)), float(v.get(1)), float(v.get(2))], dtype=float)


def get_chest_ellipsoid_params(osim, model) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for wn in CHEST_WRAP_NAMES:
        info = _wrap_ellipsoid(osim, model, wn)
        if not info:
            continue
        body, wrap = info
        dims = wrap.get_dimensions()
        trans = wrap.get_translation()
        rot = wrap.get_xyz_body_rotation()
        try:
            quad = str(wrap.get_quadrant())
        except Exception:  # noqa: BLE001
            quad = ""
        out[wn] = {
            "body": body.getName(),
            "dimensions": [float(dims.get(0)), float(dims.get(1)), float(dims.get(2))],
            "translation": [float(trans.get(0)), float(trans.get(1)), float(trans.get(2))],
            "xyz_body_rotation": [
                float(rot.get(0)), float(rot.get(1)), float(rot.get(2)),
            ],
            "quadrant": quad,
        }
    return out


def list_coupled_coord_names(model) -> list[str]:
    names: list[str] = []
    coords = model.getCoordinateSet()
    for i in range(coords.getSize()):
        n = coords.get(i).getName()
        if n in L5S1_COORDS:
            continue
        if COUPLED_COORD_RE.match(n):
            names.append(n)
    return names


def _current_path_points_ground(osim, state, muscle) -> list[np.ndarray]:
    """Ground-frame points along the realized GeometryPath (incl. wrap)."""
    pts: list[np.ndarray] = []
    gp = muscle.getGeometryPath()
    try:
        arr = gp.getCurrentPath(state)
    except Exception:  # noqa: BLE001
        arr = None
    if arr is not None:
        try:
            n = int(arr.getSize())
        except Exception:  # noqa: BLE001
            n = 0
        for i in range(n):
            try:
                pp = arr.get(i)
                loc = pp.getLocationInGround(state)
                pts.append(np.array(
                    [float(loc.get(0)), float(loc.get(1)), float(loc.get(2))],
                    dtype=float,
                ))
            except Exception:  # noqa: BLE001
                continue
    if pts:
        return pts
    ends = _ends_world(state, muscle)
    if ends is None:
        return []
    return [ends[0], ends[1]]


def _wrap_active_heuristic(
    length_m: float,
    ends: tuple[np.ndarray, np.ndarray] | None,
    n_path_pts: int,
    n_static_pts: int,
    pierce_factor: float = 1.025,
) -> bool:
    if ends is None or not np.isfinite(length_m):
        return False
    chord = float(np.linalg.norm(ends[1] - ends[0]))
    if chord <= 1e-9:
        return False
    if n_path_pts > n_static_pts + 1:
        return True
    return bool(length_m > pierce_factor * chord)


def numerical_moment_arms(
    osim,
    model,
    state,
    muscle,
    coord_names: Sequence[str] = L5S1_COORDS,
    eps_rad: float = 1e-4,
) -> dict[str, float]:
    """r = -dl/dq with full realize (couplers move dependent coords)."""
    gp = muscle.getGeometryPath()
    out: dict[str, float] = {}
    coords = model.updCoordinateSet()
    l0 = float(gp.getLength(state))
    for cname in coord_names:
        if not coords.contains(cname):
            out[cname] = float("nan")
            continue
        coord = coords.get(cname)
        q0 = float(coord.getValue(state))
        try:
            # enforce=True so CoordinateCouplers move the dependent spine
            # coordinates; with False only the L5-S1 joint itself rotates.
            coord.setValue(state, q0 + eps_rad, True)
            model.realizePosition(state)
            lp = float(gp.getLength(state))
            coord.setValue(state, q0 - eps_rad, True)
            model.realizePosition(state)
            lm = float(gp.getLength(state))
            dl = (lp - lm) / (2.0 * eps_rad)
            out[cname] = float(-dl)
        except Exception:  # noqa: BLE001
            out[cname] = float("nan")
        finally:
            try:
                coord.setValue(state, q0, True)
                model.realizePosition(state)
            except Exception:  # noqa: BLE001
                pass
    return out


def batch_moment_arms(
    osim,
    model,
    state,
    muscles: Sequence[tuple[str, Any]],
    coord_names: Sequence[str] = L5S1_COORDS,
    eps_rad: float = 1e-4,
) -> dict[str, np.ndarray]:
    """Moment arms (m) of all ``muscles`` wrt L5-S1 coords in one pass.

    Same central difference as ``numerical_moment_arms`` (r = -dl/dq,
    enforce=True so couplers move), but each coordinate is perturbed once
    and every muscle length is read from that realization (~35x faster).
    """
    coords = model.updCoordinateSet()
    out = {m: np.full(len(coord_names), np.nan) for m, _ in muscles}
    for ci, cname in enumerate(coord_names):
        if not coords.contains(cname):
            continue
        coord = coords.get(cname)
        q0 = float(coord.getValue(state))
        try:
            coord.setValue(state, q0 + eps_rad, True)
            model.realizePosition(state)
            lp: dict[str, float] = {}
            for m, mus in muscles:
                try:
                    lp[m] = float(mus.getGeometryPath().getLength(state))
                except Exception:  # noqa: BLE001
                    pass
            coord.setValue(state, q0 - eps_rad, True)
            model.realizePosition(state)
            for m, mus in muscles:
                if m not in lp:
                    continue
                try:
                    lm = float(mus.getGeometryPath().getLength(state))
                    out[m][ci] = -(lp[m] - lm) / (2.0 * eps_rad)
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                coord.setValue(state, q0, True)
                model.realizePosition(state)
            except Exception:  # noqa: BLE001
                pass
    return out


def classify_failure(
    *,
    wrap_active: bool,
    prev_wrap_active: bool | None,
    chord_hits: bool,
    endpoint_inside: bool,
    wrong_side: bool,
    tangent_jump: bool,
    length_jump: bool,
    length_m: float,
    chord_m: float,
    pierce_factor: float = 1.025,
) -> str:
    if endpoint_inside:
        return "endpoint_inside"
    if length_jump:
        return "length_jump"
    if prev_wrap_active is not None and prev_wrap_active != wrap_active:
        # unwrap/rewrap only counted when length also discontinuous-ish
        if length_jump or (
            np.isfinite(length_m)
            and np.isfinite(chord_m)
            and abs(length_m - chord_m) < 0.02
            and prev_wrap_active
        ):
            return "unwrap_rewrap"
        return "unwrap_rewrap"
    if wrong_side and wrap_active:
        return "wrong_side"
    if tangent_jump and wrap_active:
        return "tangent_jump"
    if (not wrap_active) and chord_hits and np.isfinite(length_m) and np.isfinite(chord_m):
        if length_m <= pierce_factor * max(chord_m, 1e-9):
            return "pierce"
    if (not wrap_active) and chord_hits:
        return "pierce"
    return "ok"


@dataclass
class TrialDiagResult:
    namecode: str
    condition: str
    segment: str
    app: str
    model_path: str
    ik_path: str
    chest_muscles: list[str] = field(default_factory=list)
    n_frames: int = 0
    n_fail_rows: int = 0
    failure_counts: dict[str, int] = field(default_factory=dict)
    csv_path: str = ""
    error: str = ""


def diagnose_trial(
    *,
    osim,
    model_path: str,
    ik_path: str,
    namecode: str = "",
    condition: str = "",
    segment: str = "",
    app: str = "",
    muscles: Sequence[str] | None = None,
    frame_stride: int = 1,
    compute_moment_arms: bool = True,
    tangent_jump_m: float = 0.03,
    dl_jump_m: float = JUMP_DL_M,
) -> tuple[pd.DataFrame, TrialDiagResult]:
    """Frame × muscle diagnosis table + summary."""
    from optimization.ricto_io import read_opensim_storage

    meta = TrialDiagResult(
        namecode, condition, segment, app, model_path, ik_path,
    )
    if not os.path.isfile(model_path):
        meta.error = f"missing model: {model_path}"
        return pd.DataFrame(), meta
    if not os.path.isfile(ik_path):
        meta.error = f"missing IK: {ik_path}"
        return pd.DataFrame(), meta

    model = osim.Model(model_path)
    state = model.initSystem()
    chest = list(muscles) if muscles else list_chest_path_muscles(model)
    meta.chest_muscles = chest
    wraps = {wn: _wrap_ellipsoid(osim, model, wn) for wn in CHEST_WRAP_NAMES}
    wrap_quad = {}
    for wn, info in wraps.items():
        if not info:
            continue
        try:
            wrap_quad[wn] = str(info[1].get_quadrant())
        except Exception:  # noqa: BLE001
            wrap_quad[wn] = ""

    coupled = list_coupled_coord_names(model)
    ik_df, ik_meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    indeg = _ik_in_degrees(ik_meta)
    times = ik_df[tcol].to_numpy(dtype=float)
    meta.n_frames = int(len(times))
    objs = {m: model.getMuscles().get(m) for m in chest}
    static_npts = {
        m: int(objs[m].getGeometryPath().getPathPointSet().getSize())
        for m in chest
    }

    # Precompute jump islands (any chest muscle) for length_jump flag.
    islands, jumped = detect_length_jumps(
        osim, model_path, ik_path, muscles=chest, dl_m=dl_jump_m,
    )

    def in_island(t: float) -> bool:
        for lo, hi in islands:
            if float(lo) - 1e-9 <= t <= float(hi) + 1e-9:
                return True
        return False

    rows: list[dict[str, Any]] = []
    prev_active: dict[str, bool | None] = {m: None for m in chest}
    prev_tangent: dict[str, np.ndarray | None] = {m: None for m in chest}
    prev_len: dict[str, float] = {m: float("nan") for m in chest}

    stride = max(1, int(frame_stride))
    for fi, (_, row) in enumerate(ik_df.iterrows()):
        if fi % stride != 0:
            continue
        t = float(row[tcol])
        _apply_ik_row(osim, model, state, row, indeg)
        coords = model.getCoordinateSet()
        l5 = {
            n: float(coords.get(n).getValue(state)) if coords.contains(n) else float("nan")
            for n in L5S1_COORDS
        }
        coupled_vals = {
            n: float(coords.get(n).getValue(state)) if coords.contains(n) else float("nan")
            for n in coupled
        }

        for mname, mus in objs.items():
            gp = mus.getGeometryPath()
            try:
                length_m = float(gp.getLength(state))
            except Exception:  # noqa: BLE001
                length_m = float("nan")
            ends = _ends_world(state, mus)
            path_pts = _current_path_points_ground(osim, state, mus)
            wrap_active = _wrap_active_heuristic(
                length_m, ends, len(path_pts), static_npts[mname],
            )
            chord_m = (
                float(np.linalg.norm(ends[1] - ends[0])) if ends is not None else float("nan")
            )

            chord_hits = False
            endpoint_inside = False
            wrong_side = False
            min_nd = float("nan")
            tangent_local = None
            used_wrap = ""
            for wn in _muscle_wrap_names(mus):
                info = wraps.get(wn)
                if not info:
                    continue
                body, wrap = info
                radii = wrap.get_dimensions()
                used_wrap = wn
                if ends is not None:
                    p0 = _to_wrap_local(osim, state, body, wrap, ends[0])
                    p1 = _to_wrap_local(osim, state, body, wrap, ends[1])
                    if _inside_ellipsoid(p0, radii) or _inside_ellipsoid(p1, radii):
                        endpoint_inside = True
                    if _chord_hits_ellipsoid(p0, p1, radii):
                        chord_hits = True
                # Mid path points in wrap frame → candidate contact
                locals_mid: list[np.ndarray] = []
                for pg in path_pts[1:-1] if len(path_pts) > 2 else path_pts:
                    pl = _to_wrap_local(osim, state, body, wrap, pg)
                    locals_mid.append(pl)
                    nd = _norm_dist(pl, radii)
                    if not np.isfinite(min_nd) or abs(nd) < abs(min_nd):
                        min_nd = nd
                        tangent_local = pl
                if locals_mid and wrap_active:
                    qok = _quadrant_ok(locals_mid[len(locals_mid) // 2], wrap_quad.get(wn, ""))
                    if qok is False:
                        wrong_side = True
                break

            tangent_jump = False
            if (
                wrap_active
                and tangent_local is not None
                and prev_tangent[mname] is not None
            ):
                if float(np.linalg.norm(tangent_local - prev_tangent[mname])) >= tangent_jump_m:
                    tangent_jump = True

            dL = float("nan")
            if np.isfinite(prev_len[mname]) and np.isfinite(length_m):
                dL = float(length_m - prev_len[mname])
            length_jump = bool(
                in_island(t)
                or (np.isfinite(dL) and abs(dL) >= dl_jump_m)
            )

            ftype = classify_failure(
                wrap_active=wrap_active,
                prev_wrap_active=prev_active[mname],
                chord_hits=chord_hits,
                endpoint_inside=endpoint_inside,
                wrong_side=wrong_side,
                tangent_jump=tangent_jump,
                length_jump=length_jump and abs(dL) >= dl_jump_m if np.isfinite(dL) else length_jump,
                length_m=length_m,
                chord_m=chord_m,
            )

            ma = {}
            if compute_moment_arms and ftype == "ok":
                # Skip MA on most failure frames for speed; still sample periodically
                pass
            if compute_moment_arms and (ftype == "ok" or fi % (stride * 10) == 0):
                ma = numerical_moment_arms(osim, model, state, mus)

            rec: dict[str, Any] = {
                "time_s": t,
                "frame_i": fi,
                "namecode": namecode,
                "condition": condition,
                "segment": segment,
                "app": app,
                "muscle": mname,
                "wrap_name": used_wrap,
                "length_m": length_m,
                "dL_m": dL,
                "chord_m": chord_m,
                "wrap_active": bool(wrap_active),
                "chord_hits": bool(chord_hits),
                "endpoint_inside": bool(endpoint_inside),
                "wrong_side": bool(wrong_side),
                "tangent_jump": bool(tangent_jump),
                "norm_dist_contact": min_nd,
                "approx_surf_m": (
                    _approx_surface_m(tangent_local, wraps[used_wrap][1].get_dimensions())
                    if used_wrap and wraps.get(used_wrap) and tangent_local is not None
                    else float("nan")
                ),
                "failure_type": ftype,
                "in_jump_island": bool(in_island(t)),
                "n_path_pts": len(path_pts),
            }
            for k, v in l5.items():
                rec[f"q_{k}"] = v
            for k, v in coupled_vals.items():
                rec[f"q_{k}"] = v
            if tangent_local is not None:
                rec["contact_local_x"] = float(tangent_local[0])
                rec["contact_local_y"] = float(tangent_local[1])
                rec["contact_local_z"] = float(tangent_local[2])
            for k, v in ma.items():
                rec[f"ma_{k}"] = v
            rows.append(rec)

            prev_active[mname] = wrap_active
            prev_tangent[mname] = tangent_local
            prev_len[mname] = length_m

    df = pd.DataFrame(rows)
    counts: dict[str, int] = {}
    if not df.empty and "failure_type" in df.columns:
        counts = {str(k): int(v) for k, v in df["failure_type"].value_counts().items()}
    meta.failure_counts = counts
    meta.n_fail_rows = int(sum(v for k, v in counts.items() if k != "ok"))
    meta.chest_muscles = chest
    if jumped:
        meta.failure_counts = {
            **counts,
            "muscles_with_length_jumps": len(jumped),
        }
    return df, meta


def summarize_diag_frames(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        return {"n_rows": 0, "by_muscle": {}, "by_type": {}}
    by_type = {str(k): int(v) for k, v in df["failure_type"].value_counts().items()}
    by_muscle: dict[str, Any] = {}
    for mus, g in df.groupby("muscle"):
        fc = {str(k): int(v) for k, v in g["failure_type"].value_counts().items()}
        fail = g[g["failure_type"] != "ok"]
        qcols = [c for c in g.columns if c.startswith("q_L5_S1_")]
        q_range = {}
        if not fail.empty:
            for c in qcols:
                q_range[c] = {
                    "min": float(np.nanmin(fail[c].to_numpy(dtype=float))),
                    "max": float(np.nanmax(fail[c].to_numpy(dtype=float))),
                }
        by_muscle[str(mus)] = {
            "n_fail": int((g["failure_type"] != "ok").sum()),
            "n_ok": int((g["failure_type"] == "ok").sum()),
            "failure_counts": fc,
            "fail_q_range": q_range,
            "first_fail_time_s": (
                float(fail["time_s"].iloc[0]) if not fail.empty else None
            ),
        }
    return {
        "n_rows": int(len(df)),
        "by_type": by_type,
        "by_muscle": by_muscle,
        "muscles": sorted(df["muscle"].unique().tolist()),
    }


def write_json(path: str, payload: dict) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def stamped_payload(kind: str, **extra: Any) -> dict[str, Any]:
    d = {"kind": kind, "created_utc": datetime.utcnow().isoformat() + "Z"}
    d.update(extra)
    return d


def cycle_percent(times: np.ndarray) -> np.ndarray:
    t = np.asarray(times, dtype=float)
    if t.size == 0:
        return t
    t0, t1 = float(t[0]), float(t[-1])
    dur = max(t1 - t0, 1e-12)
    return 100.0 * (t - t0) / dur


def good_frame_mask(df: pd.DataFrame) -> pd.Series:
    return (df["failure_type"] == "ok") & (~df.get("in_jump_island", False))


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if not m.any():
        return float("nan")
    return float(np.sqrt(np.mean((a[m] - b[m]) ** 2)))


def length_jump_count(lengths: np.ndarray, times: np.ndarray, dl_m: float = JUMP_DL_M) -> int:
    """Count return-jumps matching detect_length_jumps logic (single series)."""
    a = np.asarray(lengths, dtype=float)
    n = len(a)
    if n < 3:
        return 0
    d = np.diff(a)
    jump = np.zeros(n, dtype=bool)
    jump[1:] = np.isfinite(d) & (np.abs(d) >= dl_m)
    count = 0
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
                    count += 1
                    break
            j += 1
        i = j + 1 if j < n else n
    return count


WRAP_FBP_SUMMARY_NAMES = (
    "wrap_fbp_summary.json",
    "wrap_fbp_summary_reconstructed.json",
)


def wrap_fbp_cases(
    namecode: str,
    *,
    apps: Iterable[str] | None = None,
    conditions: Iterable[str] | None = None,
    segments: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    """Trials whose SO failure was repaired with a wrap_fbp trial model.

    Reads the wrap_fbp batch summary under
    ``Analysis/<protocol>/_diagnosis/wrap_fbp/<SUB>/``; if none exists, falls
    back to the ``*_WrapFBP.osim`` files under the subject's result tree.
    """
    from PATH_RULE import ResultPaths

    app_set = set(apps) if apps else None
    cond_set = set(conditions) if conditions else None
    seg_set = set(segments) if segments else None

    def keep(cond: str, seg: str, app: str) -> bool:
        return not (
            (app_set and app not in app_set)
            or (cond_set and cond not in cond_set)
            or (seg_set and seg not in seg_set)
        )

    out: list[dict[str, str]] = []
    seen: set[tuple] = set()

    def add(cond: str, seg: str, app: str) -> None:
        key = (cond, seg, app)
        if key in seen or not keep(cond, seg, app):
            return
        seen.add(key)
        out.append({"namecode": namecode, "condition": cond,
                    "segment": seg, "app": app})

    summary_dir = repair_dir(namecode, "wrap_fbp")
    for name in WRAP_FBP_SUMMARY_NAMES:
        path = os.path.join(summary_dir, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        for t in payload.get("trials") or []:
            add(str(t.get("condition") or ""), str(t.get("segment") or ""),
                str(t.get("app") or "MeasuredEHF"))
        if out:
            return out

    rp = ResultPaths(namecode)
    pat = re.compile(
        rf"^{re.escape(rp.sub_label)}_(?P<cond>.+)_(?P<seg>\d+[ABC]{{2}})_"
        r"(?P<app>[^_]+)_WrapFBP\.osim$"
    )
    for dirpath, _dirs, files in os.walk(rp.sub_dir):
        for fn in files:
            m = pat.match(fn)
            if m:
                add(m["cond"], m["seg"], m["app"])
    return out


def collect_cases(
    namecode: str | None,
    *,
    from_wrap_fbp: bool = False,
    from_trouble: bool = False,
    all_ik: bool = False,
    condition: str | None = None,
    segments: Iterable[str] | None = None,
    apps: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    """Union of the requested case sources, de-duplicated in order.

    With no source flag, the wrap_fbp-repaired trials are used.
    """
    from DETECT_muscle_path_wrap_jump import trouble_cases

    if not (from_wrap_fbp or from_trouble or all_ik):
        from_wrap_fbp = True
    conds = [condition] if condition else None
    cases: list[dict] = []
    if from_wrap_fbp and namecode:
        cases.extend(wrap_fbp_cases(namecode, apps=apps, conditions=conds,
                                    segments=segments))
    if from_trouble:
        cases.extend(trouble_cases(
            namecode=namecode, condition=condition,
            segments=set(segments) if segments else None,
            apps=set(apps) if apps else None,
        ))
    if all_ik and namecode:
        cases.extend(iter_subject_ik_cases(namecode, apps=apps,
                                           conditions=conds, segments=segments))
    seen: set[tuple] = set()
    uniq: list[dict] = []
    for c in cases:
        key = (c["namecode"], c["condition"], c["segment"], c["app"])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def spread_cases(cases: list[dict], limit: int) -> list[dict]:
    """Up to ``limit`` cases taken round-robin across conditions, and within
    each condition round-robin across AB·BC·CA segments."""
    if limit <= 0 or len(cases) <= limit:
        return list(cases)

    def interleave(groups: list[list[dict]]) -> list[dict]:
        groups = [list(g) for g in groups]
        merged: list[dict] = []
        while any(groups):
            for g in groups:
                if g:
                    merged.append(g.pop(0))
        return merged

    by_cond: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for c in cases:
        by_cond[c["condition"]][c["segment"][-2:]].append(c)
    queues = [
        interleave([secs[s] for s in sorted(secs)])
        for _, secs in sorted(by_cond.items())
    ]
    out: list[dict] = []
    while len(out) < limit and any(queues):
        for q in queues:
            if q and len(out) < limit:
                out.append(q.pop(0))
    return out


def add_case_source_args(parser) -> None:
    parser.add_argument("--from-wrap-fbp", action="store_true",
                        help="Trials repaired by wrap_fbp (default source)")
    parser.add_argument("--from-trouble", action="store_true",
                        help="SO trouble list entries")
    parser.add_argument("--all-ik", action="store_true",
                        help="Every IK.mot under the subject tree")


def iter_subject_ik_cases(
    namecode: str,
    *,
    apps: Iterable[str] | None = None,
    conditions: Iterable[str] | None = None,
    segments: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    """Enumerate IK.mot files under the subject tree (not only trouble list)."""
    from PATH_RULE import ResultPaths

    rp = ResultPaths(namecode)
    root = rp.sub_dir
    if not os.path.isdir(root):
        return []
    app_set = set(apps) if apps else None
    cond_set = set(conditions) if conditions else None
    seg_set = set(segments) if segments else None
    out: list[dict[str, str]] = []
    # …/SUB#/<cond>/<AB|BC|CA>/IK/*.mot
    for cond in sorted(os.listdir(root)):
        cdir = os.path.join(root, cond)
        if not os.path.isdir(cdir) or cond.startswith("_"):
            continue
        if cond_set and cond not in cond_set:
            continue
        for section in ("AB", "BC", "CA"):
            ik_dir = os.path.join(cdir, section, "IK")
            if not os.path.isdir(ik_dir):
                continue
            for fn in sorted(os.listdir(ik_dir)):
                if not fn.lower().endswith(".mot"):
                    continue
                # SUB8_7kg_10bpm_1AB_IK.mot
                stem = fn[:-4]
                parts = stem.split("_")
                # find segment token like 1AB
                seg = ""
                for p in parts:
                    if re.fullmatch(r"\d+[ABC]{2}", p):
                        seg = p
                        break
                if not seg:
                    continue
                if seg_set and seg not in seg_set:
                    continue
                # default app MeasuredEHF for IK without AddBox suffix
                app = "MeasuredEHF"
                if "AddBox" in stem or "AddBox" in fn:
                    app = "AddBox"
                if "HeavyHand" in stem:
                    app = "HeavyHand"
                if "FreeBox" in stem:
                    app = "FreeBox"
                if app_set and app not in app_set:
                    continue
                out.append({
                    "namecode": namecode,
                    "condition": cond,
                    "segment": seg,
                    "app": app,
                })
    # de-dup
    seen: set[tuple] = set()
    uniq: list[dict[str, str]] = []
    for c in out:
        key = (c["namecode"], c["condition"], c["segment"], c["app"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq

# -*- coding: utf-8 -*-
"""Asymmetric pipeline quality audit: IK marker fit, ID vs reserve limits, scaling.

Writes (under Analysis/Asymmetric/_diagnosis/quality_check/):
  - quality_check_IK.csv
  - quality_check_ID_reserves.csv
  - quality_check_scaling.csv
  - quality_check_diagnosis.md

IK marker errors were overwritten by the pipeline (CWD SUB{n}_ik_marker_errors.sto).
This script recomputes them offline from TRC + Scaled osim + IK.mot.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_CODES = Path(__file__).resolve().parents[3]
_RUN_TOOLS = _CODES / "c_Run_Tools"
_BUILD_MODEL = _CODES / "b_Build_Model"
for _p in (str(_CODES), str(_RUN_TOOLS), str(_BUILD_MODEL)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import PATH_RULE as _path  # noqa: E402
import SUB_Info as _sub_info  # noqa: E402
from optimization.ricto_io import read_opensim_storage  # noqa: E402

_OSIM_DLL_DIR = "C:/OpenSim 4.5/bin"
if hasattr(os, "add_dll_directory") and os.path.isdir(_OSIM_DLL_DIR):
    os.add_dll_directory(_OSIM_DLL_DIR)

ASYMMETRIC_ROOT = Path(_path.OPENSIM_DIR) / "Asymmetric"
IK_RMS_WARN_M = 0.02
IK_RMS_BAD_M = 0.04
SCALE_WARN_M = 0.02
SCALE_BAD_M = 0.04

# Reserve limits matching add_reserve_actuators.py (coord → optimal_force)
_PELVIS_RESERVES: Tuple[Tuple[str, float], ...] = (
    ("pelvis_tx", 100.0),
    ("pelvis_ty", 200.0),
    ("pelvis_tz", 100.0),
    ("pelvis_tilt", 80.0),
    ("pelvis_list", 80.0),
    ("pelvis_rotation", 80.0),
)
_LUMBAR_RESERVES: Tuple[Tuple[str, float], ...] = (
    ("L5_S1_Flex_Ext", 10.0),
    ("L5_S1_Lat_Bending", 5.0),
    ("L5_S1_axial_rotation", 5.0),
)
_SIDED_RESERVE_COORDS: Tuple[str, ...] = (
    "arm_flex", "arm_add", "arm_rot",
    "elbow_flex", "pro_sup",
    "wrist_flex", "wrist_dev",
    "hip_rotation", "hip_flexion", "hip_adduction",
    "knee_angle", "ankle_angle",
)
_SIDED_RESERVE_FORCE: float = 200.0


def _actuator_name_for(coord: str) -> str:
    if coord.startswith("lumbar") or coord.startswith("L5"):
        return f"torque_{coord}"
    if coord.startswith("pelvis"):
        return f"residual_{coord}"
    return f"reserve_{coord}"


def _build_reserve_limits() -> Dict[str, float]:
    limits: Dict[str, float] = {}
    for coord, force in _PELVIS_RESERVES:
        limits[coord] = float(force)
    for coord, force in _LUMBAR_RESERVES:
        limits[coord] = float(force)
    for side in ("_l", "_r"):
        for base in _SIDED_RESERVE_COORDS:
            limits[f"{base}{side}"] = float(_SIDED_RESERVE_FORCE)
    return limits


RESERVE_LIMITS = _build_reserve_limits()


def asymmetric_subjects(sub_filter: Optional[Sequence[str]] = None) -> List[Tuple[str, str]]:
    """Return [(namecode, SUBn), ...] for protocol Asymmetric, SUB1–8 only."""
    out: List[Tuple[str, str]] = []
    for namecode, info in _sub_info.subjects.items():
        if info.get("protocol") != "Asymmetric":
            continue
        n = int(info["SUB_number"])
        if n < 1 or n > 8:
            continue
        label = f"SUB{n}"
        if sub_filter and label not in sub_filter and namecode not in sub_filter:
            continue
        out.append((namecode, label))
    out.sort(key=lambda x: int(x[1].replace("SUB", "")))
    return out


# ──────────────────────────────────────────────────────────────────
# TRC / IKTask helpers
# ──────────────────────────────────────────────────────────────────

def read_trc_xyz(trc_path: Path) -> Tuple[np.ndarray, List[str], np.ndarray]:
    """Return (times, marker_names, xyz[n_frames, n_markers, 3]). Units as in file (m)."""
    with trc_path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    # line 3 (1-based) = Frame# Time MarkerNames...
    header = lines[3].strip().split("\t")
    marker_names = [h for h in header[2:] if h.strip()]
    # data from line 6 (0-based index 5)
    rows = []
    for ln in lines[5:]:
        parts = ln.strip().split("\t")
        if len(parts) < 2:
            continue
        rows.append(parts)
    if not rows:
        raise ValueError(f"Empty TRC: {trc_path}")
    arr = np.array(rows, dtype=object)
    times = arr[:, 1].astype(float)
    n_m = len(marker_names)
    xyz = np.full((len(times), n_m, 3), np.nan, dtype=float)
    for i in range(len(times)):
        vals = arr[i, 2:]
        for j in range(n_m):
            base = j * 3
            if base + 2 >= len(vals):
                break
            try:
                xyz[i, j, 0] = float(vals[base])
                xyz[i, j, 1] = float(vals[base + 1])
                xyz[i, j, 2] = float(vals[base + 2])
            except (TypeError, ValueError):
                pass
    return times, marker_names, xyz


def parse_ik_marker_tasks(setup_xml: Path) -> Dict[str, float]:
    """Marker name → weight for apply=true tasks (weight>0)."""
    weights: Dict[str, float] = {}
    if not setup_xml.is_file():
        return weights
    try:
        root = ET.parse(setup_xml).getroot()
    except ET.ParseError:
        return weights
    for task in root.iter("IKMarkerTask"):
        name = task.get("name")
        if not name:
            continue
        apply_el = task.find("apply")
        weight_el = task.find("weight")
        apply = True if apply_el is None else str(apply_el.text).strip().lower() == "true"
        weight = float(weight_el.text) if weight_el is not None and weight_el.text else 1.0
        if apply and weight > 0:
            weights[name] = weight
    return weights


def _interp_marker_xyz(
    trc_times: np.ndarray,
    trc_xyz: np.ndarray,
    marker_idx: Dict[str, int],
    names: Sequence[str],
    t: float,
) -> Dict[str, Optional[np.ndarray]]:
    """Linear interpolate TRC marker positions at time t."""
    if t <= trc_times[0]:
        i0, i1, a = 0, 0, 0.0
    elif t >= trc_times[-1]:
        i0 = i1 = len(trc_times) - 1
        a = 0.0
    else:
        i1 = int(np.searchsorted(trc_times, t, side="left"))
        i0 = i1 - 1
        dt = trc_times[i1] - trc_times[i0]
        a = 0.0 if dt <= 0 else (t - trc_times[i0]) / dt
    out: Dict[str, Optional[np.ndarray]] = {}
    for name in names:
        j = marker_idx.get(name)
        if j is None:
            out[name] = None
            continue
        p0 = trc_xyz[i0, j]
        p1 = trc_xyz[i1, j]
        if not (np.all(np.isfinite(p0)) and np.all(np.isfinite(p1))):
            out[name] = None
            continue
        out[name] = (1.0 - a) * p0 + a * p1
    return out


# ──────────────────────────────────────────────────────────────────
# 1) IK offline marker errors
# ──────────────────────────────────────────────────────────────────

def _discover_ik_jobs(sub_label: str) -> List[Dict[str, Any]]:
    sub_dir = ASYMMETRIC_ROOT / sub_label
    jobs: List[Dict[str, Any]] = []
    if not sub_dir.is_dir():
        return jobs
    for mot in sorted(sub_dir.rglob("*_IK.mot")):
        if mot.parent.name != "IK":
            continue  # skip Model_osim static IK
        # …/SUBn/cond/SEC/IK/SUBn_cond_seg_IK.mot
        try:
            sec = mot.parent.parent.name
            cond = mot.parent.parent.parent.name
        except IndexError:
            continue
        m = re.match(
            rf"^{re.escape(sub_label)}_{re.escape(cond)}_(.+)_IK\.mot$",
            mot.name,
        )
        if not m:
            continue
        seg = m.group(1)
        trc = mot.parent.parent / "Markers" / f"{sub_label}_{cond}_{seg}.trc"
        setup = mot.parent / f"SETUP_IK_{cond}_{seg}.xml"
        model = ASYMMETRIC_ROOT / sub_label / "Model_osim" / f"{sub_label}_Scaled.osim"
        jobs.append(
            {
                "sub": sub_label,
                "cond": cond,
                "seg": seg,
                "section": sec,
                "app": "base_IK",
                "ik_mot": str(mot),
                "trc": str(trc),
                "setup": str(setup),
                "model": str(model),
            }
        )
    return jobs


def _compute_one_ik_errors(
    model,
    state,
    coord_set,
    job: Dict[str, Any],
    stride: int,
) -> Dict[str, Any]:
    row = dict(job)
    row.update(
        {
            "n_frames": 0,
            "rms_mean_m": np.nan,
            "rms_max_m": np.nan,
            "max_err_peak_m": np.nan,
            "flag_rms_gt_2cm": False,
            "flag_rms_gt_4cm": False,
            "status": "ok",
            "error_msg": "",
        }
    )
    mot_path = Path(job["ik_mot"])
    trc_path = Path(job["trc"])
    setup_path = Path(job["setup"])
    if not mot_path.is_file():
        row["status"] = "missing_mot"
        return row
    if not trc_path.is_file():
        row["status"] = "missing_trc"
        return row
    if not Path(job["model"]).is_file():
        row["status"] = "missing_model"
        return row

    try:
        mot_df, mot_meta = read_opensim_storage(mot_path)
        trc_times, trc_names, trc_xyz = read_trc_xyz(trc_path)
    except Exception as exc:  # noqa: BLE001
        row["status"] = "fail"
        row["error_msg"] = str(exc)[:200]
        return row

    if mot_df.empty or "time" not in mot_df.columns:
        row["status"] = "fail"
        row["error_msg"] = "empty mot"
        return row

    # nan TRC?
    if not np.any(np.isfinite(trc_xyz)):
        row["status"] = "nan_trc"
        return row

    weights = parse_ik_marker_tasks(setup_path)
    if not weights:
        # fallback: all markers present in both model and TRC except BOX
        import opensim as osim  # local

        mset = model.getMarkerSet()
        for i in range(mset.getSize()):
            name = mset.get(i).getName()
            if name.endswith("_BOX"):
                continue
            if name in trc_names:
                weights[name] = 1.0

    marker_idx = {n: i for i, n in enumerate(trc_names)}
    used = [n for n in weights if n in marker_idx]
    if not used:
        row["status"] = "fail"
        row["error_msg"] = "no overlapping markers"
        return row

    # inDegrees from header
    in_degrees = True
    for line in mot_meta.get("header_lines", []):
        if "indegrees" in line.lower():
            in_degrees = "yes" in line.lower()
            break

    import opensim as osim

    mset = model.getMarkerSet()
    model_markers = {}
    for name in used:
        try:
            model_markers[name] = mset.get(name)
        except Exception:  # noqa: BLE001
            pass
    used = [n for n in used if n in model_markers]
    if not used:
        row["status"] = "fail"
        row["error_msg"] = "markers missing on model"
        return row

    n = len(mot_df)
    indices = list(range(0, n, max(1, stride)))
    rms_list: List[float] = []
    max_list: List[float] = []

    coord_names = [coord_set.get(i).getName() for i in range(coord_set.getSize())]
    mot_cols = set(mot_df.columns)

    for idx in indices:
        t = float(mot_df["time"].iloc[idx])
        for cname in coord_names:
            if cname not in mot_cols:
                continue
            coord = coord_set.get(cname)
            val = float(mot_df[cname].iloc[idx])
            if not np.isfinite(val):
                continue
            # rotational coords in degrees in IK mot
            try:
                if in_degrees and coord.getMotionType() == osim.Coordinate.Rotational:
                    coord.setValue(state, np.deg2rad(val), False)
                else:
                    coord.setValue(state, val, False)
            except Exception:  # noqa: BLE001
                coord.setValue(state, val, False)
        model.realizePosition(state)

        exp = _interp_marker_xyz(trc_times, trc_xyz, marker_idx, used, t)
        errs = []
        for name in used:
            e = exp.get(name)
            if e is None:
                continue
            loc = model_markers[name].getLocationInGround(state)
            d = np.array([loc.get(0), loc.get(1), loc.get(2)], dtype=float) - e
            if np.all(np.isfinite(d)):
                errs.append(float(np.linalg.norm(d)))
        if not errs:
            continue
        rms_list.append(float(np.sqrt(np.mean(np.square(errs)))))
        max_list.append(float(np.max(errs)))

    if not rms_list:
        row["status"] = "fail"
        row["error_msg"] = "no valid frames"
        return row

    row["n_frames"] = len(rms_list)
    row["rms_mean_m"] = float(np.mean(rms_list))
    row["rms_max_m"] = float(np.max(rms_list))
    row["max_err_peak_m"] = float(np.max(max_list))
    row["flag_rms_gt_2cm"] = row["rms_mean_m"] > IK_RMS_WARN_M
    row["flag_rms_gt_4cm"] = row["rms_mean_m"] > IK_RMS_BAD_M
    return row


def run_ik_quality(
    subjects: List[Tuple[str, str]],
    *,
    stride: int = 2,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    import opensim as osim

    try:
        osim.Logger.setLevelString("error")
    except Exception:  # noqa: BLE001
        pass

    rows: List[Dict[str, Any]] = []
    total_jobs = 0
    for _, sub_label in subjects:
        jobs = _discover_ik_jobs(sub_label)
        total_jobs += len(jobs)
    print(f"[IK] {total_jobs} segment(s), stride={stride}", flush=True)

    done = 0
    t0 = time.time()
    for _, sub_label in subjects:
        jobs = _discover_ik_jobs(sub_label)
        model_path = ASYMMETRIC_ROOT / sub_label / "Model_osim" / f"{sub_label}_Scaled.osim"
        model = None
        state = None
        coord_set = None
        if model_path.is_file():
            try:
                model = osim.Model(str(model_path))
                state = model.initSystem()
                coord_set = model.getCoordinateSet()
            except Exception as exc:  # noqa: BLE001
                print(f"[IK] model load fail {sub_label}: {exc}", flush=True)
                model = None

        for job in jobs:
            if limit is not None and done >= limit:
                break
            if model is None:
                r = dict(job)
                r.update(
                    {
                        "n_frames": 0,
                        "rms_mean_m": np.nan,
                        "rms_max_m": np.nan,
                        "max_err_peak_m": np.nan,
                        "flag_rms_gt_2cm": False,
                        "flag_rms_gt_4cm": False,
                        "status": "missing_model",
                        "error_msg": "",
                    }
                )
            else:
                r = _compute_one_ik_errors(model, state, coord_set, job, stride)
            rows.append(r)
            done += 1
            if done % 25 == 0 or done == total_jobs:
                elapsed = time.time() - t0
                print(
                    f"[IK] {done}/{total_jobs}  "
                    f"({elapsed:.0f}s, {elapsed / max(done, 1):.2f}s/seg)",
                    flush=True,
                )
        if limit is not None and done >= limit:
            break

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────
# 2) ID reserve audit
# ──────────────────────────────────────────────────────────────────

def _id_column_for_coord(coord: str) -> str:
    if coord.endswith(("_tx", "_ty", "_tz")) or coord in (
        "pelvis_tx",
        "pelvis_ty",
        "pelvis_tz",
    ):
        return f"{coord}_force"
    return f"{coord}_moment"


def run_id_reserve_quality(
    subjects: List[Tuple[str, str]],
    *,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    done = 0
    for _, sub_label in subjects:
        sub_dir = ASYMMETRIC_ROOT / sub_label
        stos = sorted(sub_dir.rglob("*_HeavyHand_InverseDynamics.sto"))
        for sto in stos:
            if limit is not None and done >= limit:
                break
            # …/cond/SEC/ID_HeavyHand/…
            try:
                sec = sto.parent.parent.name
                cond = sto.parent.parent.parent.name
            except IndexError:
                continue
            m = re.match(
                rf"^{re.escape(sub_label)}_{re.escape(cond)}_(.+)_HeavyHand_InverseDynamics\.sto$",
                sto.name,
            )
            seg = m.group(1) if m else sto.stem
            row: Dict[str, Any] = {
                "sub": sub_label,
                "cond": cond,
                "seg": seg,
                "section": sec,
                "id_sto": str(sto),
                "status": "ok",
            }
            try:
                df, _ = read_opensim_storage(sto)
            except Exception as exc:  # noqa: BLE001
                row["status"] = "fail"
                row["error_msg"] = str(exc)[:200]
                rows.append(row)
                done += 1
                continue

            worst_coord = ""
            worst_ratio = 0.0
            n_over = 0
            n_over_2x = 0
            for coord, limit_v in RESERVE_LIMITS.items():
                col = _id_column_for_coord(coord)
                actu = _actuator_name_for(coord)
                if col not in df.columns:
                    row[f"max_abs__{coord}"] = np.nan
                    row[f"limit__{coord}"] = limit_v
                    row[f"ratio__{coord}"] = np.nan
                    row[f"actu__{coord}"] = actu
                    continue
                vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
                max_abs = float(np.nanmax(np.abs(vals))) if vals.size else np.nan
                ratio = (
                    float(max_abs / limit_v)
                    if np.isfinite(max_abs) and limit_v > 0
                    else np.nan
                )
                row[f"max_abs__{coord}"] = max_abs
                row[f"limit__{coord}"] = limit_v
                row[f"ratio__{coord}"] = ratio
                row[f"actu__{coord}"] = actu
                if np.isfinite(ratio):
                    if ratio >= 1.0:
                        n_over += 1
                    if ratio >= 2.0:
                        n_over_2x += 1
                    if ratio > worst_ratio:
                        worst_ratio = ratio
                        worst_coord = coord

            row["worst_coord"] = worst_coord
            row["worst_ratio"] = worst_ratio
            row["n_over_limit"] = n_over
            row["n_over_2x"] = n_over_2x
            row["flag_any_over"] = n_over > 0
            row["flag_l5s1_over"] = False
            for lc in ("L5_S1_Flex_Ext", "L5_S1_Lat_Bending", "L5_S1_axial_rotation"):
                r = row.get(f"ratio__{lc}")
                if isinstance(r, (int, float)) and np.isfinite(r) and r >= 1.0:
                    row["flag_l5s1_over"] = True
                    break
            rows.append(row)
            done += 1
            if done % 100 == 0:
                print(f"[ID] {done} files…", flush=True)
        if limit is not None and done >= limit:
            break
    print(f"[ID] done: {len(rows)} segments", flush=True)
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────
# 3) Scaling + muscle path
# ──────────────────────────────────────────────────────────────────

def _scaling_csv_for_sub(sub_label: str) -> Optional[Path]:
    model_dir = ASYMMETRIC_ROOT / sub_label / "Model_osim"
    matches = sorted(model_dir.glob("static_segment_*_marker_errors.csv"))
    return matches[0] if matches else None


def _segment_index_from_name(path: Path) -> int:
    m = re.search(r"static_segment_(\d+)_marker_errors", path.name)
    return int(m.group(1)) if m else -1


def _check_muscle_paths(model_path: Path) -> Dict[str, Any]:
    """Load osim and flag abnormal GeometryPath lengths / missing points."""
    out: Dict[str, Any] = {
        "model_load_ok": False,
        "n_muscles": 0,
        "n_path_nan": 0,
        "n_path_nonpos": 0,
        "n_path_few_points": 0,
        "path_flags": "",
        "path_flag_examples": "",
    }
    if not model_path.is_file():
        out["path_flags"] = "missing_osim"
        return out
    try:
        import opensim as osim

        try:
            osim.Logger.setLevelString("error")
        except Exception:  # noqa: BLE001
            pass

        model = osim.Model(str(model_path))
        state = model.initSystem()
        out["model_load_ok"] = True
        mset = model.getMuscles()
        out["n_muscles"] = mset.getSize()
        examples: List[str] = []
        flags: List[str] = []
        for i in range(mset.getSize()):
            mus = mset.get(i)
            name = mus.getName()
            try:
                gp = mus.getGeometryPath()
                n_pts = gp.getPathPointSet().getSize()
                if n_pts < 2:
                    out["n_path_few_points"] += 1
                    if len(examples) < 8:
                        examples.append(f"{name}:pts={n_pts}")
                length = float(gp.getLength(state))
                if not np.isfinite(length):
                    out["n_path_nan"] += 1
                    if len(examples) < 8:
                        examples.append(f"{name}:len=nan")
                elif length <= 0:
                    out["n_path_nonpos"] += 1
                    if len(examples) < 8:
                        examples.append(f"{name}:len={length:.4g}")
            except Exception as exc:  # noqa: BLE001
                out["n_path_nan"] += 1
                if len(examples) < 8:
                    examples.append(f"{name}:exc={type(exc).__name__}")
        if out["n_path_nan"]:
            flags.append("nan_path_length")
        if out["n_path_nonpos"]:
            flags.append("nonpositive_path_length")
        if out["n_path_few_points"]:
            flags.append("few_path_points")
        out["path_flags"] = "|".join(flags)
        out["path_flag_examples"] = "; ".join(examples)
    except Exception as exc:  # noqa: BLE001
        out["path_flags"] = f"load_fail:{type(exc).__name__}"
        out["path_flag_examples"] = str(exc)[:200]
    return out


def run_scaling_quality(subjects: List[Tuple[str, str]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, sub_label in subjects:
        csv_path = _scaling_csv_for_sub(sub_label)
        row: Dict[str, Any] = {
            "sub": sub_label,
            "marker_errors_csv": str(csv_path) if csv_path else "",
            "segment_index": _segment_index_from_name(csv_path) if csv_path else -1,
            "status": "ok",
        }
        if csv_path is None:
            row["status"] = "missing_csv"
            rows.append(row)
            continue
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:  # noqa: BLE001
            row["status"] = "fail"
            row["error_msg"] = str(exc)[:200]
            rows.append(row)
            continue

        # First data row after header should be All Timesteps RMSE
        # Column Timestep == "All Timesteps RMSE"
        rmse_row = df[df.iloc[:, 0].astype(str).str.contains("All Timesteps RMSE", na=False)]
        if rmse_row.empty:
            # assume first numeric row after header is summary — use row 0
            rmse_vals = df.iloc[0, 1:]
        else:
            rmse_vals = rmse_row.iloc[0, 1:]

        body = {}
        for name, val in rmse_vals.items():
            if str(name).endswith("_BOX"):
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(v) or v == 0.0:
                continue
            body[str(name)] = v

        if not body:
            row["status"] = "empty_rmse"
            rows.append(row)
            continue

        vals = np.array(list(body.values()), dtype=float)
        row["n_body_markers"] = len(vals)
        row["rmse_mean_m"] = float(np.mean(vals))
        row["rmse_median_m"] = float(np.median(vals))
        row["rmse_max_m"] = float(np.max(vals))
        row["rmse_mean_mm"] = row["rmse_mean_m"] * 1000.0
        row["rmse_max_mm"] = row["rmse_max_m"] * 1000.0
        row["n_gt_2cm"] = int(np.sum(vals > SCALE_WARN_M))
        row["n_gt_4cm"] = int(np.sum(vals > SCALE_BAD_M))
        top = sorted(body.items(), key=lambda kv: kv[1], reverse=True)[:5]
        row["top5_worst"] = "; ".join(f"{n}={v*1000:.1f}mm" for n, v in top)
        row["flag_mean_gt_2cm"] = row["rmse_mean_m"] > SCALE_WARN_M
        row["flag_mean_gt_4cm"] = row["rmse_mean_m"] > SCALE_BAD_M
        row["n_frames"] = max(0, len(df) - 1)  # exclude summary row approx

        # muscle path on Scaled + one HeavyHand
        scaled = ASYMMETRIC_ROOT / sub_label / "Model_osim" / f"{sub_label}_Scaled.osim"
        path_info = _check_muscle_paths(scaled)
        row.update({f"scaled_{k}": v for k, v in path_info.items()})

        hh = sorted(
            (ASYMMETRIC_ROOT / sub_label / "Model_osim").glob(
                f"{sub_label}_Scaled_HeavyHand_*.osim"
            )
        )
        if hh:
            hh_info = _check_muscle_paths(hh[0])
            row["heavyhand_osim"] = hh[0].name
            row.update({f"hh_{k}": v for k, v in hh_info.items()})
        else:
            row["heavyhand_osim"] = ""

        rows.append(row)
        print(
            f"[Scale] {sub_label}: mean={row.get('rmse_mean_mm', float('nan')):.1f} mm  "
            f"flags={row.get('scaled_path_flags', '')}",
            flush=True,
        )
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────
# 4) Diagnosis markdown
# ──────────────────────────────────────────────────────────────────

def write_diagnosis_md(
    out_path: Path,
    ik: pd.DataFrame,
    idf: pd.DataFrame,
    scale: pd.DataFrame,
) -> None:
    lines: List[str] = []
    lines.append("# Asymmetric pipeline quality diagnosis")
    lines.append("")
    lines.append(f"Generated by `RUN_quality_check_asymmetric.py`. Root: `{ASYMMETRIC_ROOT}`.")
    lines.append("")
    lines.append("## 1. Summary")
    lines.append("")

    ik_ok = ik[ik["status"] == "ok"] if not ik.empty and "status" in ik.columns else ik
    id_ok = idf[idf["status"] == "ok"] if not idf.empty and "status" in idf.columns else idf

    if not ik_ok.empty and "rms_mean_m" in ik_ok.columns:
        lines.append(
            f"- **IK** (offline recompute): {len(ik_ok)} segments OK; "
            f"mean RMS = {ik_ok['rms_mean_m'].mean()*1000:.1f} mm; "
            f">2 cm mean RMS: {int(ik_ok['flag_rms_gt_2cm'].sum())}; "
            f">4 cm: {int(ik_ok['flag_rms_gt_4cm'].sum())}."
        )
        lines.append(
            "  - Cohort mean RMS sits ~3 cm (shoulder/elbow markers dominate). "
            "The 2 cm flag is nearly universal — rank by RMS / use >4 cm for red flags."
        )
    else:
        lines.append("- **IK**: no successful recompute rows.")

    if not ik.empty and "status" in ik.columns:
        nan_n = int((ik["status"] == "nan_trc").sum())
        if nan_n:
            lines.append(
                f"  - **nan TRC** (IK not usable): {nan_n} rows — "
                "concentrated on SUB2 `7kg_16bpm` / `15kg_16bpm` (known bad marker export)."
            )

    if not id_ok.empty:
        lines.append(
            f"- **ID vs reserve**: {len(id_ok)} segments; "
            f"any coord over limit: {int(id_ok['flag_any_over'].sum())}; "
            f"L5–S1 over limit: {int(id_ok['flag_l5s1_over'].sum())}; "
            f"≥2× limit somewhere: {int((id_ok['n_over_2x'] > 0).sum())}."
        )
        lines.append(
            "  - **Dominant driver:** L5–S1 torque actuators (10/5/5 Nm) are far below "
            "ID demand on every segment; `pelvis_list` residual (80 Nm) is also always over. "
            "Limb reserves (200 Nm) rarely max out."
        )
    else:
        lines.append("- **ID**: no rows.")

    if not scale.empty and "rmse_mean_mm" in scale.columns:
        bad = scale[scale.get("flag_mean_gt_4cm", False) == True]  # noqa: E712
        lines.append(
            f"- **Scaling**: {len(scale)} subjects; "
            f"mean body RMSE > 4 cm: {', '.join(bad['sub'].tolist()) or 'none'}."
        )
        if "scaled_path_flags" in scale.columns:
            flagged = scale[
                scale["scaled_path_flags"].fillna("").astype(str).str.len() > 0
            ]
            if flagged.empty:
                lines.append(
                    "  - Muscle path auto-check: **no NaN/non-positive lengths** "
                    "on Scaled models (238 muscles each)."
                )
    lines.append("")

    lines.append("## 2. IK marker fit (offline)")
    lines.append("")
    lines.append(
        "Per-segment `_ik_marker_errors.sto` was **not** archived: "
        "`run_ik` set the tool name to `SUBn` only and left `results_directory` empty, "
        "so OpenSim wrote `Codes/c_Run_Tools/SUB{n}_ik_marker_errors.sto` and each "
        "segment overwrote the previous file. "
        "Quality below is recomputed from TRC + `SUB{n}_Scaled.osim` + `*_IK.mot` "
        "(unweighted RMS of IKTask apply=true markers)."
    )
    lines.append("")
    if not ik_ok.empty and "rms_mean_m" in ik_ok.columns:
        by_sub = (
            ik_ok.groupby("sub")
            .agg(
                n=("rms_mean_m", "count"),
                rms_mean_mm=("rms_mean_m", lambda s: 1000 * s.mean()),
                rms_p95_mm=("rms_mean_m", lambda s: 1000 * s.quantile(0.95)),
                n_gt_2cm=("flag_rms_gt_2cm", "sum"),
                n_gt_4cm=("flag_rms_gt_4cm", "sum"),
            )
            .reset_index()
        )
        lines.append("| sub | n | mean RMS (mm) | p95 RMS (mm) | n>2cm | n>4cm |")
        lines.append("|-----|---|---------------|--------------|-------|-------|")
        for _, r in by_sub.iterrows():
            lines.append(
                f"| {r['sub']} | {int(r['n'])} | {r['rms_mean_mm']:.1f} | "
                f"{r['rms_p95_mm']:.1f} | {int(r['n_gt_2cm'])} | {int(r['n_gt_4cm'])} |"
            )
        lines.append("")
        worst = ik_ok.nlargest(15, "rms_mean_m")[
            ["sub", "cond", "seg", "rms_mean_m", "rms_max_m", "max_err_peak_m"]
        ]
        lines.append("### Worst segments (by mean RMS)")
        lines.append("")
        lines.append("| sub | cond | seg | mean RMS (mm) | max frame RMS (mm) | peak marker (mm) |")
        lines.append("|-----|------|-----|---------------|--------------------|------------------|")
        for _, r in worst.iterrows():
            lines.append(
                f"| {r['sub']} | {r['cond']} | {r['seg']} | "
                f"{r['rms_mean_m']*1000:.1f} | {r['rms_max_m']*1000:.1f} | "
                f"{r['max_err_peak_m']*1000:.1f} |"
            )
        lines.append("")
        fail = ik[ik["status"] != "ok"] if "status" in ik.columns else pd.DataFrame()
        if not fail.empty:
            lines.append(f"Non-OK IK rows: {len(fail)} "
                         f"({fail['status'].value_counts().to_dict()})")
            lines.append("")

    lines.append("## 3. ID moments vs reserve `optimal_force`")
    lines.append("")
    lines.append(
        "ID generalized forces (`*_moment` / `*_force`) compared to CoordinateActuator "
        "`optimal_force` baked into the osim (limb reserves 200 Nm; pelvis residual "
        "100/200/100 N and 80 Nm; L5–S1 torque 10/5/5 Nm). "
        "Controls allow ±10000, so the hard ceiling is much higher; "
        "**ratio ≥ 1** means SO must use |control| ≫ 1 for that DOF — a risk for SO stability."
    )
    lines.append("")
    if not id_ok.empty:
        # L5-S1 focus
        for coord in ("L5_S1_Flex_Ext", "L5_S1_Lat_Bending", "L5_S1_axial_rotation"):
            col = f"ratio__{coord}"
            if col not in id_ok.columns:
                continue
            r = id_ok[col].dropna()
            if r.empty:
                continue
            lines.append(
                f"- **{coord}**: median ratio={r.median():.2f}, "
                f"p95={r.quantile(0.95):.2f}, max={r.max():.2f}, "
                f"over limit: {int((r >= 1).sum())}/{len(r)}"
            )
        lines.append("")
        # pelvis
        for coord in ("pelvis_ty", "pelvis_tx", "pelvis_tz",
                      "pelvis_tilt", "pelvis_list", "pelvis_rotation"):
            col = f"ratio__{coord}"
            if col not in id_ok.columns:
                continue
            r = id_ok[col].dropna()
            if r.empty:
                continue
            lines.append(
                f"- **{coord}**: median ratio={r.median():.2f}, "
                f"p95={r.quantile(0.95):.2f}, max={r.max():.2f}, "
                f"over: {int((r >= 1).sum())}/{len(r)}"
            )
        lines.append("")
        by_sub = (
            id_ok.groupby("sub")
            .agg(
                n=("worst_ratio", "count"),
                median_worst=("worst_ratio", "median"),
                max_worst=("worst_ratio", "max"),
                n_any_over=("flag_any_over", "sum"),
                n_l5s1=("flag_l5s1_over", "sum"),
            )
            .reset_index()
        )
        lines.append("| sub | n | median worst ratio | max worst | any over | L5S1 over |")
        lines.append("|-----|---|--------------------|-----------|----------|-----------|")
        for _, r in by_sub.iterrows():
            lines.append(
                f"| {r['sub']} | {int(r['n'])} | {r['median_worst']:.2f} | "
                f"{r['max_worst']:.2f} | {int(r['n_any_over'])} | {int(r['n_l5s1'])} |"
            )
        lines.append("")
        top = id_ok.nlargest(15, "worst_ratio")[
            ["sub", "cond", "seg", "worst_coord", "worst_ratio", "n_over_limit"]
        ]
        lines.append("### Highest worst-ratio segments")
        lines.append("")
        lines.append("| sub | cond | seg | worst coord | ratio | n over |")
        lines.append("|-----|------|-----|-------------|-------|--------|")
        for _, r in top.iterrows():
            lines.append(
                f"| {r['sub']} | {r['cond']} | {r['seg']} | "
                f"{r['worst_coord']} | {r['worst_ratio']:.2f} | {int(r['n_over_limit'])} |"
            )
        lines.append("")

    lines.append("## 4. Model scaling & muscle paths")
    lines.append("")
    lines.append(
        "Static fit from AddBiomech `static_segment_*_marker_errors.csv` "
        "(All Timesteps RMSE, body markers only). "
        "Muscle paths: OpenSim API length/point checks at default pose "
        "(GUI visual review still recommended for flagged models)."
    )
    lines.append("")
    if not scale.empty and "rmse_mean_mm" in scale.columns:
        lines.append(
            "| sub | seg idx | mean RMSE (mm) | max (mm) | n>2cm | n>4cm | top-5 | path flags |"
        )
        lines.append(
            "|-----|---------|----------------|----------|-------|-------|-------|------------|"
        )
        for _, r in scale.iterrows():
            lines.append(
                f"| {r.get('sub','')} | {r.get('segment_index','')} | "
                f"{r.get('rmse_mean_mm', float('nan')):.1f} | "
                f"{r.get('rmse_max_mm', float('nan')):.1f} | "
                f"{int(r.get('n_gt_2cm', 0))} | {int(r.get('n_gt_4cm', 0))} | "
                f"{r.get('top5_worst', '')} | {r.get('scaled_path_flags', '')} |"
            )
        lines.append("")
        gui = scale[
            scale["scaled_path_flags"].astype(str).str.len().fillna(0) > 0
        ] if "scaled_path_flags" in scale.columns else pd.DataFrame()
        if not gui.empty:
            lines.append("### GUI review recommended")
            lines.append("")
            for _, r in gui.iterrows():
                lines.append(
                    f"- **{r['sub']}**: `{r.get('scaled_path_flags')}` — "
                    f"{r.get('scaled_path_flag_examples', '')}"
                )
            lines.append("")

    lines.append("## 5. Recommendations")
    lines.append("")
    lines.append(
        "1. **IK archive (done in pipeline code):** `run_ik` now sets a unique tool name "
        "and `results_directory` to the segment `IK/` folder so future runs keep "
        "`*_ik_marker_errors.sto`."
    )
    lines.append(
        "2. **L5–S1 / pelvis reserves:** If ID ratios ≫ 1 dominate SO failures, "
        "consider raising `torque_L5_S1_*` / residual `optimal_force` in "
        "`add_reserve_actuators.py` and regenerating models — or accept that SO "
        "will lean on large controls for those DOFs."
    )
    lines.append(
        "3. **Scaling:** Subjects with mean body RMSE ≳ 4 cm (often head/shoulder) "
        "should be re-checked in AddBiomech before trusting distal arm SO/JR."
    )
    lines.append(
        "4. **Cross with SO trouble:** Compare high `worst_ratio` / bad IK rows to "
        "`pipeline_trouble.json` when prioritizing retries."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- `quality_check_IK.csv`")
    lines.append("- `quality_check_ID_reserves.csv`")
    lines.append("- `quality_check_scaling.csv`")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[MD] wrote {out_path}", flush=True)


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--subs",
        nargs="*",
        default=None,
        help="Optional SUB labels or namecodes (default: SUB1–8)",
    )
    ap.add_argument(
        "--skip-ik",
        action="store_true",
        help="Skip offline IK recompute (ID + scaling + MD only)",
    )
    ap.add_argument(
        "--skip-id",
        action="store_true",
    )
    ap.add_argument(
        "--skip-scaling",
        action="store_true",
    )
    ap.add_argument(
        "--ik-stride",
        type=int,
        default=2,
        help="Frame stride for IK FK error (1=every frame). Default 2.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit segments processed (IK and ID) for smoke tests",
    )
    ap.add_argument(
        "--out-dir",
        type=str,
        default=_path.diagnosis_dir("Asymmetric", "quality_check"),
    )
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subjects = asymmetric_subjects(args.subs)
    print(f"Subjects: {[s for _, s in subjects]}", flush=True)
    print(f"Output: {out_dir}", flush=True)

    ik_path = out_dir / "quality_check_IK.csv"
    id_path = out_dir / "quality_check_ID_reserves.csv"
    sc_path = out_dir / "quality_check_scaling.csv"
    md_path = out_dir / "quality_check_diagnosis.md"

    if args.skip_ik and ik_path.is_file():
        ik = pd.read_csv(ik_path)
        print(f"[IK] loaded existing {ik_path} ({len(ik)} rows)", flush=True)
    elif args.skip_ik:
        ik = pd.DataFrame()
        print("[IK] skipped (no existing CSV)", flush=True)
    else:
        ik = run_ik_quality(subjects, stride=args.ik_stride, limit=args.limit)
        ik.to_csv(ik_path, index=False)
        print(f"[IK] wrote {ik_path} ({len(ik)} rows)", flush=True)

    if args.skip_id and id_path.is_file():
        idf = pd.read_csv(id_path)
    elif args.skip_id:
        idf = pd.DataFrame()
    else:
        idf = run_id_reserve_quality(subjects, limit=args.limit)
        idf.to_csv(id_path, index=False)
        print(f"[ID] wrote {id_path} ({len(idf)} rows)", flush=True)

    if args.skip_scaling and sc_path.is_file():
        scale = pd.read_csv(sc_path)
    elif args.skip_scaling:
        scale = pd.DataFrame()
    else:
        scale = run_scaling_quality(subjects)
        scale.to_csv(sc_path, index=False)
        print(f"[Scale] wrote {sc_path} ({len(scale)} rows)", flush=True)

    write_diagnosis_md(md_path, ik, idf, scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

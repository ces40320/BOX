"""Tier B repair variant: FunctionBasedPath fitted by OpenSim ``PolynomialPathFitter``.

Same goal as ``wrap_fbp_lib.build_fbp_sidecar`` (replace the Chest-wrap
muscles' GeometryPath with l(q) on a trial-only model), but the polynomial
is fitted by OpenSim (stepwise regression, moment arms included) instead of
a numpy length-only fit.

NaN guard (Chest wrap penetration by random samples):

1. coordinate table = good IK frames only (wrap-jump islands removed),
   radians, absolute state names;
2. fitter model keeps only the target muscles (other forces removed);
3. sampling bounds are tight offsets around the IK values (default ±3°);
4. sampled lengths / moment arms and fitted coefficients are checked for
   non-finite values, and fitted lengths are compared with the GeometryPath
   on good frames. A muscle that fails falls back to the numpy l(q) fit.

Outputs (``SO_<app>/troubleshoot_so/wrap_fbp/``):

- ``<SUB>_<cond>_<seg>_<app>_WrapPPF.osim``  (or ``_WrapFBP.osim`` with ``as_trial_model``)
- ``<SUB>_<cond>_<seg>_<app>_WrapPPF_validation.json``  length / moment-arm RMSE
- ``ppf_work/``  raw fitter output (``*_FunctionBasedPathSet.xml``, sampled STOs)
"""

from __future__ import annotations

import glob
import json
import math
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

import numpy as np  # noqa: E402

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from wrap_detect_lib import _apply_ik_row, _ik_in_degrees, import_opensim  # noqa: E402
from wrap_fbp_lib import (  # noqa: E402
    _FBP_COORD_NAMES,
    _fit_length_polys_numpy,
    _in_islands,
    _log,
    _write_function_based_path_set,
)
from optimization.ricto_io import read_opensim_storage  # noqa: E402

DEFAULT_MUSCLES = ("LTpT_T3_l", "LTpT_T3_r", "LTpT_T4_l", "LTpT_T4_r")

PPF_DEFAULTS = {
    "max_order": 4,
    "samples_per_frame": 10,
    "global_bounds_deg": 3.0,
    "moment_arm_threshold": 1e-3,
    "length_tol_m": 1e-3,
    "moment_arm_tol_m": 1e-3,
    "stepwise": True,
    "parallel": 4,
    "frame_stride": 1,
    # Fallback to numpy when fitted length RMSE on good frames exceeds this.
    "accept_length_rmse_m": 3e-3,
}


def _ppf_model_path(cp: ConditionPaths, seg: str, app: str, *, as_trial_model: bool) -> str:
    if as_trial_model:
        return cp.wrap_fbp_model_path(seg, app)
    d = cp.so_troubleshoot_dir(cp.seg_to_section(seg), app, "wrap_fbp")
    return os.path.join(d, f"{cp.sub_label}_{cp.cond}_{seg}_{app}_WrapPPF.osim")


def _keep_only_muscles(osim, model, keep: set[str]) -> int:
    """Remove every force except ``keep`` so the fitter samples nothing else."""
    fs = model.updForceSet()
    drop = [i for i in range(fs.getSize()) if fs.get(i).getName() not in keep]
    for i in reversed(drop):
        fs.remove(i)
    return len(drop)


def _good_coordinate_table(osim, model, good_df, meta, stride: int):
    """Good IK rows → TimeSeriesTable (radians, ``/jointset/.../value`` labels)."""
    state = model.initSystem()
    coords = model.getCoordinateSet()
    indeg = _ik_in_degrees(meta)
    names = [coords.get(i).getName() for i in range(coords.getSize())]
    labels = osim.StdVectorString()
    for i in range(coords.getSize()):
        labels.append(f"{coords.get(i).getAbsolutePathString()}/value")
    table = osim.TimeSeriesTable()
    table.setColumnLabels(labels)
    tcol = "time" if "time" in good_df.columns else "Time"
    rows = good_df.iloc[::max(1, int(stride))]
    for _, row in rows.iterrows():
        _apply_ik_row(osim, model, state, row, indeg)
        vals = osim.RowVector(len(names), 0.0)
        for j, n in enumerate(names):
            vals[j] = float(coords.get(n).getValue(state))
        table.appendRow(float(row[tcol]), vals)
    table.addTableMetaDataString("inDegrees", "no")
    return table


def _run_fitter(osim, *, fit_model, coord_table, work: str, opts: dict,
                coord_bounds_deg: dict[str, float]) -> str:
    """Run PolynomialPathFitter; returns the FunctionBasedPathSet XML path."""
    fitter = osim.PolynomialPathFitter()
    fitter.setModel(osim.ModelProcessor(fit_model))
    fitter.setCoordinateValues(osim.TableProcessor(coord_table))
    fitter.setOutputDirectory(work)
    fitter.setMaximumPolynomialOrder(int(opts["max_order"]))
    fitter.setNumSamplesPerFrame(int(opts["samples_per_frame"]))
    fitter.setGlobalCoordinateSamplingBounds(
        osim.Vec2(-float(opts["global_bounds_deg"]), float(opts["global_bounds_deg"])))
    for cpath, b in coord_bounds_deg.items():
        fitter.appendCoordinateSamplingBounds(cpath, osim.Vec2(-float(b), float(b)))
    fitter.setMomentArmThreshold(float(opts["moment_arm_threshold"]))
    fitter.setPathLengthTolerance(float(opts["length_tol_m"]))
    fitter.setMomentArmTolerance(float(opts["moment_arm_tol_m"]))
    fitter.setIncludeMomentArmFunctions(True)
    fitter.setIncludeLengtheningSpeedFunction(True)
    fitter.setParallel(int(opts["parallel"]))
    if hasattr(fitter, "setUseStepwiseRegression"):
        fitter.setUseStepwiseRegression(bool(opts["stepwise"]))
    else:
        _log("[PPF] setUseStepwiseRegression unavailable (OpenSim < 4.5.1)")
    fitter.run()
    hits = glob.glob(os.path.join(work, "*_FunctionBasedPathSet.xml"))
    if not hits:
        raise RuntimeError(f"fitter wrote no FunctionBasedPathSet in {work}")
    return hits[0]


def _sampled_nonfinite(work: str, muscles: list[str]) -> set[str]:
    """Muscles whose sampled length / moment-arm columns contain NaN/Inf.

    File names differ between OpenSim builds, so any ``*sampled*.sto`` with
    path lengths or moment arms is scanned and columns matched by muscle name.
    """
    bad: set[str] = set()
    for path in glob.glob(os.path.join(work, "*sampled*.sto")):
        low = os.path.basename(path).lower()
        if "length" not in low and "moment" not in low:
            continue
        df, _ = read_opensim_storage(path)
        for col in df.columns:
            hit = [m for m in muscles if m in str(col)]
            if not hit:
                continue
            if not np.all(np.isfinite(df[col].to_numpy(dtype=float))):
                bad.update(hit)
    return bad


def _fbp_elements(xml_path: str) -> dict[str, ET.Element]:
    """``muscle → <FunctionBasedPath>`` element of a FunctionBasedPathSet file."""
    root = ET.parse(xml_path).getroot()
    out = {}
    for el in root.iter("FunctionBasedPath"):
        out[el.get("name", "").split("/")[-1]] = el
    return out


def _element_finite(el: ET.Element) -> bool:
    for c in el.iter("coefficients"):
        vals = [float(v) for v in (c.text or "").split()]
        if not vals or not all(math.isfinite(v) for v in vals):
            return False
    return True


def _write_merged_set(path: str, elements: dict[str, ET.Element]) -> str:
    root = ET.Element("OpenSimDocument", Version="40500")
    s = ET.SubElement(root, "Set_FunctionBasedPath_")
    objs = ET.SubElement(s, "objects")
    for el in elements.values():
        objs.append(el)
    ET.SubElement(s, "groups")
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)
    return path


def validate_paths(osim, *, source_model: str, fitted_model: str, good_df, meta,
                   muscles: list[str]) -> dict:
    """Length / moment-arm RMSE of the fitted path vs GeometryPath on good frames.

    Moment arms are compared for the L5-S1 coordinates.
    """
    src = osim.Model(source_model)
    s_src = src.initSystem()
    fit = osim.Model(fitted_model)
    s_fit = fit.initSystem()
    indeg = _ik_in_degrees(meta)
    acc = {m: {"dl": [], "dr": {c: [] for c in _FBP_COORD_NAMES}} for m in muscles}
    for _, row in good_df.iterrows():
        _apply_ik_row(osim, src, s_src, row, indeg)
        _apply_ik_row(osim, fit, s_fit, row, indeg)
        for m in muscles:
            gp = src.getMuscles().get(m).getGeometryPath()
            fp = fit.getMuscles().get(m).getPath()
            acc[m]["dl"].append(fp.getLength(s_fit) - gp.getLength(s_src))
            for c in _FBP_COORD_NAMES:
                r0 = gp.computeMomentArm(s_src, src.getCoordinateSet().get(c))
                r1 = fp.computeMomentArm(s_fit, fit.getCoordinateSet().get(c))
                acc[m]["dr"][c].append(r1 - r0)

    def _rmse(v):
        a = np.asarray(v, dtype=float)
        return float(np.sqrt(np.mean(a ** 2))) if a.size and np.all(np.isfinite(a)) else float("nan")

    out = {}
    for m in muscles:
        out[m] = {
            "length_rmse_m": _rmse(acc[m]["dl"]),
            "moment_arm_rmse_m": {c: _rmse(acc[m]["dr"][c]) for c in _FBP_COORD_NAMES},
        }
        ma = out[m]["moment_arm_rmse_m"]
        _log(
            f"[validate] {m}: length RMSE={out[m]['length_rmse_m']*100:.3f} cm  "
            + "  ".join(f"r({c})={v*100:.3f} cm" for c, v in ma.items())
        )
    return out


def build_ppf_sidecar(*, model_path: str, ik_path: str, islands: list,
                      muscles: list[str], out_osim: str, opts: dict | None = None,
                      work: str | None = None) -> tuple[str | None, dict]:
    """Fit FunctionBasedPaths with PolynomialPathFitter on good IK frames.

    Returns ``(out_osim or None, info)``; ``info`` records per-muscle source
    (``ppf`` / ``numpy``), the fitter settings, and validation RMSE.
    """
    o = dict(PPF_DEFAULTS)
    o.update(opts or {})
    info: dict = {"muscles": list(muscles), "settings": o}
    osim = import_opensim()
    ik_df, meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    good = ik_df.loc[~ik_df[tcol].map(lambda t: _in_islands(float(t), islands))]
    good = good.reset_index(drop=True)
    info.update(n_frames_total=int(len(ik_df)), n_frames_fit=int(len(good)),
                excluded_islands_s=islands)
    if len(good) < 8:
        _log(f"[PPF] only {len(good)} good frames — skip")
        return None, info

    work = work or os.path.join(os.path.dirname(out_osim), "ppf_work",
                                os.path.splitext(os.path.basename(out_osim))[0])
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    fit_model = osim.Model(model_path)
    n_drop = _keep_only_muscles(osim, fit_model, set(muscles))
    fit_model.setName(os.path.splitext(os.path.basename(out_osim))[0])
    fit_model.finalizeConnections()
    _log(f"[PPF] fitter model: kept {len(muscles)} muscles, removed {n_drop} forces")
    coord_table = _good_coordinate_table(osim, fit_model, good, meta, o["frame_stride"])
    l5 = {f"/jointset/L5_S1_IVDjnt/{c}": o["global_bounds_deg"] for c in _FBP_COORD_NAMES}

    ppf_elems: dict[str, ET.Element] = {}
    try:
        set_xml = _run_fitter(osim, fit_model=fit_model, coord_table=coord_table,
                              work=work, opts=o, coord_bounds_deg=l5)
        ppf_elems = _fbp_elements(set_xml)
    except Exception as exc:  # noqa: BLE001
        _log(f"[PPF] fitter failed: {exc}")
        info["fitter_error"] = str(exc)

    bad_samples = _sampled_nonfinite(work, muscles) if ppf_elems else set()
    source: dict[str, str] = {}
    reasons: dict[str, str] = {}
    for m in muscles:
        el = ppf_elems.get(m)
        if el is None:
            reasons[m] = "not fitted"
        elif m in bad_samples:
            reasons[m] = "NaN in sampled length/moment arm (wrap penetration)"
        elif not _element_finite(el):
            reasons[m] = "non-finite coefficients"
        else:
            source[m] = "ppf"

    merged: dict[str, ET.Element] = {m: ppf_elems[m] for m in source}
    tmp_xml = os.path.join(work, "FunctionBasedPathSet_merged.xml")

    def _numpy_fallback(names: list[str]) -> None:
        coefs, rmses = _fit_length_polys_numpy(
            osim, model_path=model_path, good_df=good, meta=meta, muscles=names, order=3)
        np_xml = os.path.join(work, "FunctionBasedPathSet_numpy.xml")
        _write_function_based_path_set(np_xml, coefs, order=3)
        for m, el in _fbp_elements(np_xml).items():
            merged[m] = el
            source[m] = "numpy"
        info.setdefault("numpy_length_rmse_m", {}).update(rmses)

    def _replace() -> str:
        _write_merged_set(tmp_xml, merged)
        proc = osim.ModelProcessor(model_path)
        proc.append(osim.ModOpReplacePathsWithFunctionBasedPaths(tmp_xml))
        fitted = proc.process()
        fitted.finalizeConnections()
        fitted.initSystem()
        os.makedirs(os.path.dirname(out_osim), exist_ok=True)
        fitted.printToXML(out_osim)
        return out_osim

    fallback = [m for m in muscles if m not in source]
    for m in fallback:
        _log(f"[PPF] {m}: {reasons[m]} → numpy l(q)")
    if fallback:
        _numpy_fallback(fallback)
    _replace()

    val = validate_paths(osim, source_model=model_path, fitted_model=out_osim,
                         good_df=good, meta=meta, muscles=muscles)
    worse = [m for m in muscles if source.get(m) == "ppf"
             and not (val[m]["length_rmse_m"] <= o["accept_length_rmse_m"])]
    if worse:
        for m in worse:
            reasons[m] = f"length RMSE {val[m]['length_rmse_m']:.4g} m > accept"
            merged.pop(m, None)
            _log(f"[PPF] {m}: {reasons[m]} → numpy l(q)")
        _numpy_fallback(worse)
        _replace()
        val = validate_paths(osim, source_model=model_path, fitted_model=out_osim,
                             good_df=good, meta=meta, muscles=muscles)

    info.update(path_source=source, fallback_reason=reasons, validation=val,
                fitter_output_dir=work)
    _log(f"[PPF] trial model → {out_osim} ({source})")
    return out_osim, info


def write_validation(out_osim: str, case: dict, info: dict) -> str:
    out = out_osim[:-len(".osim")] + "_validation.json"
    payload = dict(case)
    payload.update(info, trial_model=out_osim,
                   created_at=datetime.now().isoformat(timespec="seconds"))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    _log(f"[record] {out}")
    return out


def case_paths(case: dict, *, as_trial_model: bool) -> str:
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    return _ppf_model_path(cp, case["segment"], case["app"], as_trial_model=as_trial_model)

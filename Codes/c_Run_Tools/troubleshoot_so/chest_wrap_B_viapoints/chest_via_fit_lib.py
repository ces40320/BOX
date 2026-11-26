"""Approach B: replace failing Chest wraps with fixed / moving via points.

Keeps GeometryPath. For each failing muscle, removes Chest PathWrap entries and
inserts 1–2 PathPoints on torso (optional lumbar1), fitted to good-frame wrap
path samples from the original model.
"""

from __future__ import annotations

import os
from typing import Any, Sequence

import numpy as np

from wrap_detect_lib import (
    CHEST_WRAP_NAMES,
    _apply_ik_row,
    import_opensim,
    list_chest_path_muscles,
)
from chest_diag_lib import (
    L5S1_COORDS,
    chest_out_dir,
    write_json,
)

DEFAULT_FAIL_MUSCLES = (
    "LTpT_T3_l", "LTpT_T3_r", "LTpT_T4_l", "LTpT_T4_r",
)


def _ik_in_degrees(meta: dict) -> bool:
    v = str(meta.get("inDegrees") or meta.get("in_degrees") or "").strip().lower()
    if v in ("yes", "true", "1"):
        return True
    if v in ("no", "false", "0"):
        return False
    return True


def _body_station(osim, state, body, p_ground: np.ndarray) -> np.ndarray:
    X_GB = body.getTransformInGround(state)
    p = X_GB.shiftBaseStationToFrame(
        osim.Vec3(float(p_ground[0]), float(p_ground[1]), float(p_ground[2]))
    )
    return np.array([p.get(0), p.get(1), p.get(2)], dtype=float)


def _current_path_ground(osim, state, muscle) -> list[np.ndarray]:
    pts: list[np.ndarray] = []
    try:
        arr = muscle.getGeometryPath().getCurrentPath(state)
        n = int(arr.getSize())
    except Exception:  # noqa: BLE001
        return pts
    for i in range(n):
        try:
            loc = arr.get(i).getLocationInGround(state)
            pts.append(np.array(
                [float(loc.get(0)), float(loc.get(1)), float(loc.get(2))],
                dtype=float,
            ))
        except Exception:  # noqa: BLE001
            continue
    return pts


def collect_wrap_path_samples(
    *,
    osim,
    model_path: str,
    ik_path: str,
    muscles: Sequence[str],
    body_names: Sequence[str] = ("torso",),
    frame_stride: int = 2,
    ok_times: set[float] | None = None,
    time_tol: float = 1e-4,
) -> dict[str, dict[str, list[np.ndarray]]]:
    """muscle → body → list of body-frame sample points from wrapped path."""
    from optimization.ricto_io import read_opensim_storage

    model = osim.Model(model_path)
    state = model.initSystem()
    ik_df, meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    indeg = _ik_in_degrees(meta)
    out: dict[str, dict[str, list[np.ndarray]]] = {
        m: {b: [] for b in body_names} for m in muscles
    }
    bodies = {b: model.getBodySet().get(b) for b in body_names
              if model.getBodySet().contains(b)}

    for fi, (_, row) in enumerate(ik_df.iterrows()):
        if fi % max(1, frame_stride) != 0:
            continue
        t = float(row[tcol])
        if ok_times is not None and not any(abs(t - ot) <= time_tol for ot in ok_times):
            continue
        _apply_ik_row(osim, model, state, row, indeg)
        for m in muscles:
            if not model.getMuscles().contains(m):
                continue
            mus = model.getMuscles().get(m)
            path = _current_path_ground(osim, state, mus)
            if len(path) < 3:
                continue
            # use mid wrap samples (exclude origin/insertion)
            mids = path[1:-1]
            # pick up to 2 representative mid points
            if len(mids) == 1:
                picks = mids
            else:
                picks = [mids[0], mids[len(mids) // 2], mids[-1]]
            for bname, body in bodies.items():
                for pg in picks:
                    out[m][bname].append(_body_station(osim, state, body, pg))
    return out


def fit_fixed_via_points(
    samples: list[np.ndarray],
    n_points: int = 2,
) -> list[list[float]]:
    """Cluster / quantile along principal axis → n fixed body-frame points."""
    if not samples:
        return [[0.0, 0.0, 0.0]] * n_points
    X = np.stack(samples, axis=0)
    mean = X.mean(axis=0)
    Xc = X - mean
    # PCA 1st axis
    try:
        _, _, vt = np.linalg.svd(Xc, full_matrices=False)
        axis = vt[0]
    except Exception:  # noqa: BLE001
        axis = np.array([0.0, 1.0, 0.0])
    proj = Xc @ axis
    qs = np.linspace(0.2, 0.8, n_points) if n_points > 1 else [0.5]
    pts = []
    for q in qs:
        thr = np.quantile(proj, q)
        # take mean of points near quantile
        band = np.abs(proj - thr) <= max(1e-4, 0.05 * np.ptp(proj))
        if not band.any():
            band = np.abs(proj - thr).argmin()
            pts.append((mean + Xc[band]).tolist())
        else:
            pts.append(X[band].mean(axis=0).tolist())
    return pts


def fit_moving_spline_1d(
    q: np.ndarray,
    points: np.ndarray,
    *,
    n_knots: int = 5,
) -> dict[str, Any]:
    """Fit per-axis piecewise linear function of scalar q (e.g. L5-S1 flex).

    Returns knot qs and xyz values (OpenSim PiecewiseLinearFunction friendly).
    """
    q = np.asarray(q, dtype=float)
    P = np.asarray(points, dtype=float)
    m = np.isfinite(q) & np.all(np.isfinite(P), axis=1)
    q, P = q[m], P[m]
    if q.size < 2:
        return {
            "q_knots": [0.0, 1.0],
            "x": [0.0, 0.0], "y": [0.0, 0.0], "z": [0.0, 0.0],
        }
    order = np.argsort(q)
    q, P = q[order], P[order]
    # unique q
    uq, idx = np.unique(q, return_index=True)
    P = P[idx]
    q = uq
    knots = np.linspace(float(q[0]), float(q[-1]), max(2, n_knots))
    xs, ys, zs = [], [], []
    for k in knots:
        # nearest / linear interp
        xs.append(float(np.interp(k, q, P[:, 0])))
        ys.append(float(np.interp(k, q, P[:, 1])))
        zs.append(float(np.interp(k, q, P[:, 2])))
    return {
        "q_knots": knots.tolist(),
        "x": xs, "y": ys, "z": zs,
        "q_min": float(q[0]),
        "q_max": float(q[-1]),
    }


def _remove_chest_wraps(muscle) -> int:
    gp = muscle.updGeometryPath()
    wset = gp.updWrapSet()
    removed = 0
    # remove from end
    for i in range(wset.getSize() - 1, -1, -1):
        pw = wset.get(i)
        try:
            wn = pw.getWrapObjectName()
        except Exception:  # noqa: BLE001
            try:
                wn = str(pw.get_wrap_object())
            except Exception:  # noqa: BLE001
                continue
        if wn in CHEST_WRAP_NAMES:
            wset.remove(i)
            removed += 1
    return removed


def _insert_path_point(osim, muscle, name: str, body, location: Sequence[float],
                       index: int | None = None) -> None:
    gp = muscle.updGeometryPath()
    pp = osim.PathPoint()
    pp.setName(name)
    pp.setParentFrame(body)
    pp.set_location(osim.Vec3(
        float(location[0]), float(location[1]), float(location[2]),
    ))
    pps = gp.updPathPointSet()
    if index is None:
        # insert before last point
        idx = max(0, pps.getSize() - 1)
    else:
        idx = index
    try:
        pps.insert(idx, pp)
    except Exception:  # noqa: BLE001
        pps.cloneAndAppend(pp)


def _insert_moving_path_point(
    osim, model, muscle, name: str, body, spline: dict, coord_name: str,
    index: int | None = None,
) -> None:
    """Insert MovingPathPoint with PiecewiseLinearFunction x/y/z of coord."""
    gp = muscle.updGeometryPath()
    mpp = osim.MovingPathPoint()
    mpp.setName(name)
    mpp.setParentFrame(body)
    coords = model.getCoordinateSet()
    if not coords.contains(coord_name):
        raise ValueError(f"missing coordinate {coord_name}")
    coord = coords.get(coord_name)
    mpp.setXCoordinate(coord)
    mpp.setYCoordinate(coord)
    mpp.setZCoordinate(coord)

    def _plf(xs, ys):
        f = osim.PiecewiseLinearFunction()
        for x, y in zip(xs, ys):
            f.addPoint(float(x), float(y))
        return f

    knots = spline["q_knots"]
    mpp.set_x_location( _plf(knots, spline["x"]))
    mpp.set_y_location( _plf(knots, spline["y"]))
    mpp.set_z_location( _plf(knots, spline["z"]))

    pps = gp.updPathPointSet()
    idx = max(0, pps.getSize() - 1) if index is None else index
    try:
        pps.insert(idx, mpp)
    except Exception:  # noqa: BLE001
        pps.cloneAndAppend(mpp)


def build_via_model(
    *,
    osim,
    baseline_model_path: str,
    out_path: str,
    muscle_specs: dict[str, dict[str, Any]],
    use_moving: bool = False,
    moving_coord: str = "L5_S1_Flex_Ext",
) -> dict[str, Any]:
    """Write subject-level model with via points for listed muscles.

    Edits the .osim XML directly: inserting SWIG-created PathPoints into a
    PathPointSet aborts inside Model.finalizeConnections (OpenSim 4.x).
    """
    from lxml import etree

    model = osim.Model(baseline_model_path)
    model.initSystem()
    bodies = {model.getBodySet().get(i).getName() for i in range(model.getBodySet().getSize())}
    coord_path = ""
    if use_moving:
        cs = model.getCoordinateSet()
        if not cs.contains(moving_coord):
            raise ValueError(f"missing coordinate {moving_coord}")
        coord_path = cs.get(moving_coord).getAbsolutePathString()

    tree = etree.parse(baseline_model_path)
    root = tree.getroot()
    report: dict[str, Any] = {"muscles": {}, "out_path": out_path}

    def _vec(v) -> str:
        return " ".join(repr(float(x)) for x in v)

    def _point_el(name: str, body_name: str, loc) -> Any:
        el = etree.Element("PathPoint", name=name)
        etree.SubElement(el, "socket_parent_frame").text = f"/bodyset/{body_name}"
        etree.SubElement(el, "location").text = _vec(loc)
        return el

    def _moving_el(name: str, body_name: str, spline: dict) -> Any:
        el = etree.Element("MovingPathPoint", name=name)
        etree.SubElement(el, "socket_parent_frame").text = f"/bodyset/{body_name}"
        for ax in ("x", "y", "z"):
            etree.SubElement(el, f"socket_{ax}_coordinate").text = coord_path
        for ax in ("x", "y", "z"):
            fn = etree.SubElement(etree.SubElement(el, f"{ax}_location"), "PiecewiseLinearFunction")
            etree.SubElement(fn, "x").text = _vec(spline["q_knots"])
            etree.SubElement(fn, "y").text = _vec(spline[ax])
        return el

    for mname, spec in muscle_specs.items():
        hits = [e for e in root.iter() if e.get("name") == mname and e.find("GeometryPath") is not None]
        if not hits:
            report["muscles"][mname] = {"error": "missing"}
            continue
        gp = hits[0].find("GeometryPath")
        n_rem = 0
        for pw in gp.findall("PathWrapSet/objects/PathWrap"):
            if (pw.findtext("wrap_object") or "").strip() in CHEST_WRAP_NAMES:
                pw.getparent().remove(pw)
                n_rem += 1
        body_name = spec.get("body", "torso")
        if body_name not in bodies:
            report["muscles"][mname] = {"error": f"missing body {body_name}"}
            continue
        objs = gp.find("PathPointSet/objects")
        n_orig = len(objs)
        points = spec.get("points") or []
        mode = spec.get("mode", "fixed")
        new_els = []
        if use_moving and mode == "moving" and "spline" in spec:
            new_els.append(_moving_el(f"{mname}_via_mov", body_name, spec["spline"]))
        else:
            new_els.extend(
                _point_el(f"{mname}_via{i}", body_name, loc) for i, loc in enumerate(points)
            )
        # torso via points go just before the insertion (last) point
        for k, el in enumerate(new_els):
            objs.insert(max(0, n_orig - 1) + k, el)
        inserted = len(new_els)
        if spec.get("lumbar_point") and "lumbar1" in bodies:
            objs.insert(
                max(0, n_orig - 2),
                _point_el(f"{mname}_via_L1", "lumbar1", spec["lumbar_point"]),
            )
            inserted += 1
        report["muscles"][mname] = {
            "removed_chest_wraps": n_rem,
            "inserted": inserted,
            "body": body_name,
            "mode": mode,
            "points": points,
        }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tree.write(out_path, xml_declaration=True, encoding="UTF-8")
    check = osim.Model(out_path)
    check.initSystem()
    return report


def fit_subject_via_points(
    *,
    namecode: str,
    baseline_model_path: str,
    ik_jobs: list[dict],
    muscles: Sequence[str] | None = None,
    n_via: int = 2,
    include_lumbar1: bool = False,
    use_moving: bool = False,
    ok_times_by_trial: dict[tuple, set[float]] | None = None,
) -> dict[str, Any]:
    osim = import_opensim()
    muscles = list(muscles) if muscles else list(DEFAULT_FAIL_MUSCLES)
    # collect samples across jobs
    all_samples: dict[str, dict[str, list[np.ndarray]]] = {
        m: {"torso": [], "lumbar1": []} for m in muscles
    }
    q_samples: dict[str, list[float]] = {m: [] for m in muscles}
    p_samples: dict[str, list[np.ndarray]] = {m: [] for m in muscles}

    bodies = ("torso", "lumbar1") if include_lumbar1 else ("torso",)
    for job in ik_jobs:
        key = (job["condition"], job["segment"], job["app"])
        ok = None if ok_times_by_trial is None else ok_times_by_trial.get(key)
        samp = collect_wrap_path_samples(
            osim=osim,
            model_path=baseline_model_path,
            ik_path=job["ik_path"],
            muscles=muscles,
            body_names=bodies,
            ok_times=ok,
        )
        for m in muscles:
            for b in bodies:
                all_samples[m][b].extend(samp.get(m, {}).get(b, []))

        # moving: also gather (q, torso point)
        if use_moving:
            from optimization.ricto_io import read_opensim_storage
            model = osim.Model(baseline_model_path)
            state = model.initSystem()
            ik_df, meta = read_opensim_storage(job["ik_path"])
            tcol = "time" if "time" in ik_df.columns else "Time"
            indeg = _ik_in_degrees(meta)
            torso = model.getBodySet().get("torso")
            for fi, (_, row) in enumerate(ik_df.iterrows()):
                if fi % 3 != 0:
                    continue
                t = float(row[tcol])
                if ok is not None and not any(abs(t - ot) <= 1e-4 for ot in ok):
                    continue
                _apply_ik_row(osim, model, state, row, indeg)
                q = float(model.getCoordinateSet().get(L5S1_COORDS[0]).getValue(state))
                for m in muscles:
                    if not model.getMuscles().contains(m):
                        continue
                    path = _current_path_ground(osim, state, model.getMuscles().get(m))
                    if len(path) < 3:
                        continue
                    mid = path[len(path) // 2]
                    p_samples[m].append(_body_station(osim, state, torso, mid))
                    q_samples[m].append(q)

    specs: dict[str, dict[str, Any]] = {}
    for m in muscles:
        pts = fit_fixed_via_points(all_samples[m]["torso"], n_points=n_via)
        spec: dict[str, Any] = {
            "body": "torso",
            "points": pts,
            "mode": "fixed",
        }
        if include_lumbar1 and all_samples[m]["lumbar1"]:
            lp = fit_fixed_via_points(all_samples[m]["lumbar1"], n_points=1)[0]
            spec["lumbar_point"] = lp
        if use_moving and q_samples[m] and p_samples[m]:
            spec["mode"] = "moving"
            spec["spline"] = fit_moving_spline_1d(
                np.asarray(q_samples[m]), np.stack(p_samples[m]),
            )
        specs[m] = spec

    from PATH_RULE import ResultPaths
    sub = ResultPaths(namecode).sub_label
    out_dir = chest_out_dir(namecode, "B")
    out_osim = os.path.join(out_dir, f"{sub}_ChestVia.osim")
    report = build_via_model(
        osim=osim,
        baseline_model_path=baseline_model_path,
        out_path=out_osim,
        muscle_specs=specs,
        use_moving=use_moving,
    )
    payload = {
        "namecode": namecode,
        "sub_label": sub,
        "out_osim": out_osim,
        "muscles": list(muscles),
        "n_via": n_via,
        "include_lumbar1": include_lumbar1,
        "use_moving": use_moving,
        "specs": specs,
        "build_report": report,
        "n_ik_jobs": len(ik_jobs),
    }
    write_json(os.path.join(out_dir, f"via_points_{sub}.json"), payload)
    return payload

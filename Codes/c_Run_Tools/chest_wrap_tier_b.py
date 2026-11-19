"""Tier B repair: trial-only FunctionBasedPath, else Chest sidecar.

The shared scaled ``.osim`` is never overwritten. Gap-fill is not used.
"""

from __future__ import annotations

import os
import shutil
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.append(CODES_DIR)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from pathlib import Path  # noqa: E402

from PATH_RULE import ConditionPaths, ResultPaths  # noqa: E402
from chest_wrap_lib import (  # noqa: E402
    CHEST_WRAP_NAMES,
    POSTERIOR_AXIS,
    POSTERIOR_SIGN,
    TIER_A_BAD_FRAC,
    TIER_A_MAX_ISLAND_S,
    import_opensim,
    repair_dir,
    scan_trial,
)
from opensim_pipeline_handlers import (  # noqa: E402
    prepare_jr_setup,
    prepare_so_setup,
    run_jr,
    run_so,
)
from optimization.ricto_io import read_opensim_storage, write_opensim_storage  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


def _in_islands(t: float, islands: list) -> bool:
    for pair in islands:
        if float(pair[0]) - 1e-9 <= t <= float(pair[1]) + 1e-9:
            return True
    return False


def _sidecar_path(cp: ConditionPaths, seg: str, app: str, tag: str) -> str:
    section = cp.seg_to_section(seg)
    d = cp.so_dir(section, app)
    os.makedirs(d, exist_ok=True)
    stem = f"{cp.sub_label}_{cp.cond}_{seg}_{app}_{tag}"
    return os.path.join(d, stem + ".osim")


def _drop_other_muscles(osim, model, keep: set[str]) -> int:
    fs = model.updForceSet()
    drop = []
    for i in range(fs.getSize()):
        force = fs.get(i)
        if osim.Muscle.safeDownCast(force) is None:
            continue
        if force.getName() not in keep:
            drop.append(i)
    for i in reversed(drop):
        fs.remove(i)
    return len(drop)


# L5_S1 coords used for lumbar erector / latissimus Chest-wrap paths.
_FBP_COORD_NAMES = (
    "L5_S1_Flex_Ext",
    "L5_S1_Lat_Bending",
    "L5_S1_axial_rotation",
)
_FBP_COORD_PATHS = (
    "/jointset/L5_S1_IVDjnt/L5_S1_Flex_Ext",
    "/jointset/L5_S1_IVDjnt/L5_S1_Lat_Bending",
    "/jointset/L5_S1_IVDjnt/L5_S1_axial_rotation",
)


def _poly_exponents(dimension: int, order: int) -> list[tuple[int, ...]]:
    """OpenSim MultivariatePolynomialFunction monomial order (last dim fastest)."""
    if dimension != 3:
        raise ValueError("only dimension=3 implemented")
    out: list[tuple[int, ...]] = []
    for nx in range(order + 1):
        for ny in range(order + 1 - nx):
            for nz in range(order + 1 - nx - ny):
                out.append((nx, ny, nz))
    return out


def _design_matrix(q: "np.ndarray", order: int):
    import numpy as np

    exps = _poly_exponents(3, order)
    A = np.empty((q.shape[0], len(exps)), dtype=float)
    for j, (nx, ny, nz) in enumerate(exps):
        A[:, j] = (q[:, 0] ** nx) * (q[:, 1] ** ny) * (q[:, 2] ** nz)
    return A, exps


def _fit_length_polys_numpy(
    osim,
    *,
    model_path: str,
    good_df,
    meta: dict,
    muscles: list[str],
    order: int = 3,
) -> dict[str, list[float]]:
    """Least-squares l(q) on good IK rows. Returns muscle → coefficients."""
    import numpy as np
    from chest_wrap_lib import _apply_ik_row, _ik_in_degrees

    model = osim.Model(model_path)
    state = model.initSystem()
    coords = model.getCoordinateSet()
    for name in _FBP_COORD_NAMES:
        if not coords.contains(name):
            raise RuntimeError(f"missing coordinate {name}")
    indeg = _ik_in_degrees(meta)
    objs = {m: model.getMuscles().get(m) for m in muscles}
    q_rows = []
    L = {m: [] for m in muscles}
    for _, row in good_df.iterrows():
        _apply_ik_row(osim, model, state, row, indeg)
        model.realizePosition(state)
        q_rows.append([float(coords.get(n).getValue(state)) for n in _FBP_COORD_NAMES])
        for m, mus in objs.items():
            L[m].append(float(mus.getGeometryPath().getLength(state)))
    q = np.asarray(q_rows, dtype=float)
    A, _ = _design_matrix(q, order)
    coefs: dict[str, list[float]] = {}
    for m in muscles:
        y = np.asarray(L[m], dtype=float)
        if not np.all(np.isfinite(y)):
            raise RuntimeError(f"non-finite GeometryPath length for {m}")
        c, *_ = np.linalg.lstsq(A, y, rcond=None)
        if not np.all(np.isfinite(c)):
            raise RuntimeError(f"non-finite polynomial coeffs for {m}")
        yhat = A @ c
        rmse = float(np.sqrt(np.mean((y - yhat) ** 2)))
        _log(f"[FBP] numpy {m}: order={order} RMSE={rmse*100:.3f} cm n={len(y)}")
        coefs[m] = [float(v) for v in c]
    return coefs


def _write_function_based_path_set(
    path: str,
    coefs: dict[str, list[float]],
    *,
    order: int,
) -> str:
    coord_paths = " ".join(_FBP_COORD_PATHS)
    objs = []
    for muscle, c in coefs.items():
        cstr = " ".join(f"{v:.16g}" for v in c)
        objs.append(
            f"""\t\t\t<FunctionBasedPath name="/forceset/{muscle}">
\t\t\t\t<coordinate_paths>{coord_paths}</coordinate_paths>
\t\t\t\t<length_function>
\t\t\t\t\t<MultivariatePolynomialFunction>
\t\t\t\t\t\t<coefficients>{cstr}</coefficients>
\t\t\t\t\t\t<dimension>3</dimension>
\t\t\t\t\t\t<order>{order}</order>
\t\t\t\t\t</MultivariatePolynomialFunction>
\t\t\t\t</length_function>
\t\t\t</FunctionBasedPath>"""
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        '<OpenSimDocument Version="40500">\n'
        "\t<Set_FunctionBasedPath_>\n"
        "\t\t<objects>\n"
        + "\n".join(objs)
        + "\n\t\t</objects>\n"
        "\t\t<groups />\n"
        "\t</Set_FunctionBasedPath_>\n"
        "</OpenSimDocument>\n"
    )
    Path(path).write_text(xml, encoding="utf-8")
    return path


def build_fbp_sidecar(
    *,
    model_path: str,
    ik_path: str,
    islands: list,
    muscles: list[str],
    out_osim: str,
    work_dir: str,
) -> str | None:
    """Fit FunctionBasedPaths on good IK frames for ``muscles`` only.

    Uses a numpy least-squares fit of ``MultivariatePolynomialFunction``
    coefficients (OpenSim monomial order). ``PolynomialPathFitter`` on this
    OpenSim 4.5 / Windows build yields NaN coeffs for most lumbar paths.
    """
    if not muscles:
        _log("[FBP] no target muscles")
        return None
    osim = import_opensim()
    os.makedirs(work_dir, exist_ok=True)
    ik_df, meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    keep_rows = ~ik_df[tcol].map(lambda t: _in_islands(float(t), islands))
    good = ik_df.loc[keep_rows].reset_index(drop=True)
    if len(good) < 8:
        _log(f"[FBP] only {len(good)} good frames — skip")
        return None
    good_mot = os.path.join(work_dir, "ik_good_frames.mot")
    write_opensim_storage(good_mot, good, meta)

    order = 3
    try:
        coefs = _fit_length_polys_numpy(
            osim,
            model_path=model_path,
            good_df=good,
            meta=meta,
            muscles=muscles,
            order=order,
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"[FBP] numpy fit failed: {exc}")
        return None

    paths_xml = os.path.join(work_dir, "FunctionBasedPathSet_numpy.xml")
    _write_function_based_path_set(paths_xml, coefs, order=order)
    proc = osim.ModelProcessor(model_path)
    proc.append(osim.ModOpReplacePathsWithFunctionBasedPaths(paths_xml))
    fitted = proc.process()
    fitted.finalizeConnections()
    fitted.initSystem()
    fitted.printToXML(out_osim)
    _log(f"[FBP] sidecar → {out_osim} ({len(coefs)} paths, numpy)")
    return out_osim


def _scale_chest(osim, model, scale: float, posterior_m: float) -> None:
    bodies = model.getBodySet()
    for bi in range(bodies.getSize()):
        body = bodies.get(bi)
        wset = body.updWrapObjectSet()
        for wi in range(wset.getSize()):
            w = wset.get(wi)
            if w.getName() not in CHEST_WRAP_NAMES:
                continue
            ell = osim.WrapEllipsoid.safeDownCast(w)
            if ell is None:
                continue
            d = ell.get_dimensions()
            ell.set_dimensions(osim.Vec3(
                d.get(0) * scale, d.get(1) * scale, d.get(2) * scale,
            ))
            if posterior_m:
                t = ell.get_translation()
                vals = [t.get(0), t.get(1), t.get(2)]
                vals[POSTERIOR_AXIS] += POSTERIOR_SIGN * posterior_m
                ell.set_translation(osim.Vec3(*vals))


def build_chest_sidecar(
    *,
    osim,
    model_path: str,
    ik_path: str,
    out_osim: str,
    namecode: str,
    condition: str,
    segment: str,
    app: str,
    baseline_bad_s: float,
) -> tuple[str | None, dict]:
    """Trial copy with a small Chest dims/translation change. Shared osim untouched."""
    candidates = [
        (1.05, 0.0),
        (1.10, 0.0),
        (1.15, 0.0),
        (1.0, 0.010),
    ]
    work = os.path.join(repair_dir(namecode), "_chest_grid")
    os.makedirs(work, exist_ok=True)
    best = None
    best_bad = baseline_bad_s
    best_info = {}
    for scale, post in candidates:
        trial_path = os.path.join(work, f"s{scale:.2f}_p{post:.3f}.osim")
        model = osim.Model(model_path)
        _scale_chest(osim, model, scale, post)
        model.finalizeConnections()
        model.initSystem()
        model.printToXML(trial_path)
        res = scan_trial(
            osim=osim,
            model_path=trial_path,
            ik_path=ik_path,
            namecode=namecode,
            condition=condition,
            segment=segment,
            app=app,
        )
        bad = float(res.severity.total_bad_s)
        _log(
            f"[Chest] scale={scale:.2f} post={post:.3f} "
            f"bad_s={bad:.3f} tier={res.tier}"
        )
        improved = bad < best_bad - 1e-6
        tier_ok = (
            res.severity.max_island_s <= TIER_A_MAX_ISLAND_S
            and res.severity.bad_frac <= TIER_A_BAD_FRAC
        )
        if improved and (best is None or bad < best_bad):
            best = (trial_path, scale, post, res)
            best_bad = bad
            best_info = {
                "scale": scale,
                "posterior_m": post,
                "bad_s": bad,
                "tier_after": res.tier,
                "reaches_tier_a_metrics": tier_ok,
            }
    if best is None or best_bad >= baseline_bad_s * 0.8:
        _log("[Chest] no candidate improved bad time by ≥20%")
        return None, best_info
    shutil.copy2(best[0], out_osim)
    _log(f"[Chest] sidecar → {out_osim}")
    return out_osim, best_info


def _run_full_so(
    case: dict,
    model_path: str,
    *,
    skip_jr: bool,
    timeout_s: float | None,
) -> None:
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    seg, app = case["segment"], case["app"]
    prepare_so_setup(cp=cp, rp=rp, seg=seg, app=app, model_path=model_path)
    run_so(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s, model_path=model_path)
    if not skip_jr:
        prepare_jr_setup(cp=cp, rp=rp, seg=seg, app=app, model_path=model_path)
        run_jr(cp=cp, rp=rp, seg=seg, app=app, timeout_s=timeout_s, model_path=model_path)


def repair_tier_b(
    case: dict,
    *,
    model_path: str,
    ik_path: str,
    islands: list,
    muscles: list[str],
    baseline_bad_s: float,
    skip_jr: bool = False,
    timeout_s: float | None = 120.0,
    dry_run: bool = False,
) -> dict:
    """FBP sidecar first, Chest patch second. Returns a status dict."""
    if str(case.get("tier") or "B") != "B":
        raise ValueError(f"repair_tier_b called for tier {case.get('tier')}")
    rp = ResultPaths(case["namecode"])
    cp = ConditionPaths(rp, case["condition"])
    work = os.path.join(
        repair_dir(case["namecode"]),
        f"{case['condition']}_{case['segment']}_{case['app']}",
    )
    os.makedirs(work, exist_ok=True)
    info = {
        "status": "tier_C",
        "gapfill_rejected_reason": "severity",
        "method": None,
        "sidecar": None,
    }
    if dry_run:
        info["status"] = "dry_run"
        return info

    fbp_path = _sidecar_path(cp, case["segment"], case["app"], "WrapFBP")
    built = build_fbp_sidecar(
        model_path=model_path,
        ik_path=ik_path,
        islands=islands,
        muscles=muscles,
        out_osim=fbp_path,
        work_dir=work,
    )
    if built:
        try:
            _run_full_so(case, built, skip_jr=skip_jr, timeout_s=timeout_s)
            info.update(status="ok", method="function_based_path", sidecar=built)
            return info
        except Exception as exc:  # noqa: BLE001
            _log(f"[FBP] SO failed: {exc}")
            info["fbp_so_error"] = str(exc)

    chest_path = _sidecar_path(cp, case["segment"], case["app"], "ChestPatch")
    osim = import_opensim()
    built_c, chest_info = build_chest_sidecar(
        osim=osim,
        model_path=model_path,
        ik_path=ik_path,
        out_osim=chest_path,
        namecode=case["namecode"],
        condition=case["condition"],
        segment=case["segment"],
        app=case["app"],
        baseline_bad_s=baseline_bad_s,
    )
    info["chest"] = chest_info
    if not built_c:
        info["status"] = "tier_C"
        info["exclude_from_primary"] = True
        return info
    if not chest_info.get("reaches_tier_a_metrics"):
        # Still a long excursion: do not pretend quality is fine.
        info["status"] = "tier_C"
        info["exclude_from_primary"] = True
        info["chest_sidecar_unaccepted"] = built_c
        return info
    try:
        _run_full_so(case, built_c, skip_jr=skip_jr, timeout_s=timeout_s)
    except Exception as exc:  # noqa: BLE001
        _log(f"[Chest] SO failed: {exc}")
        info["status"] = "tier_C"
        info["exclude_from_primary"] = True
        info["chest_so_error"] = str(exc)
        return info
    info.update(status="ok", method="chest_sidecar", sidecar=built_c)
    return info

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


def build_fbp_sidecar(
    *,
    model_path: str,
    ik_path: str,
    islands: list,
    muscles: list[str],
    out_osim: str,
    work_dir: str,
) -> str | None:
    """Fit FunctionBasedPaths on good IK frames for ``muscles`` only."""
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

    model = osim.Model(model_path)
    n_drop = _drop_other_muscles(osim, model, set(muscles))
    _log(f"[FBP] dropped {n_drop} muscles; fitting {len(muscles)}")
    reduced = os.path.join(work_dir, "reduced_for_fit.osim")
    model.finalizeConnections()
    model.initSystem()
    model.printToXML(reduced)

    out_dir = os.path.join(work_dir, "fbp_out")
    os.makedirs(out_dir, exist_ok=True)
    fitter = osim.PolynomialPathFitter()
    fitter.setModel(osim.ModelProcessor(reduced))
    fitter.setCoordinateValues(osim.TableProcessor(good_mot))
    fitter.setOutputDirectory(out_dir)
    fitter.setNumSamplesPerFrame(5)
    fitter.setMaximumPolynomialOrder(4)
    fitter.setMinimumPolynomialOrder(2)
    try:
        fitter.setGlobalCoordinateSamplingBounds(osim.Vec2(-5, 5))
    except Exception:  # noqa: BLE001
        pass
    try:
        fitter.run()
    except Exception as exc:  # noqa: BLE001
        _log(f"[FBP] fit failed: {exc}")
        return None

    xmls = sorted(Path(out_dir).glob("*FunctionBasedPath*.xml"))
    if not xmls:
        xmls = sorted(Path(out_dir).rglob("*.xml"))
    if not xmls:
        _log("[FBP] no FunctionBasedPath XML written")
        return None
    paths_xml = str(xmls[0])
    proc = osim.ModelProcessor(model_path)
    proc.append(osim.ModOpReplacePathsWithFunctionBasedPaths(paths_xml))
    fitted = proc.process()
    fitted.finalizeConnections()
    fitted.initSystem()
    fitted.printToXML(out_osim)
    _log(f"[FBP] sidecar → {out_osim}")
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

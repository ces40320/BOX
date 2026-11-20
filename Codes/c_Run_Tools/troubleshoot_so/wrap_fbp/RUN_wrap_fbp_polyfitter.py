"""Chest-wrap muscles → FunctionBasedPath via OpenSim ``PolynomialPathFitter``.

For each SO trouble trial: find wrap-jump islands from IK
(``detect_length_jumps``), fit the jumping thoracic longissimus paths
(default LTpT_T3/T4 L/R) with ``PolynomialPathFitter`` on good frames only,
fall back to the numpy l(q) fit per muscle when the fitter gives NaN or a
poor length fit, and write a trial model + validation JSON (length and
L5-S1 moment-arm RMSE vs GeometryPath on good frames).

By default the model is written as ``*_WrapPPF.osim`` next to the existing
``*_WrapFBP.osim`` so both can be compared; ``--as-trial-model`` writes it
to the ``_WrapFBP.osim`` name that the pipeline picks up, and ``--run-so``
then reruns SO (+JR unless ``--skip-jr``).

Example::

    python wrap_fbp/RUN_wrap_fbp_polyfitter.py --from-trouble --namecode 260526_PJM --apps MeasuredEHF
    python wrap_fbp/RUN_wrap_fbp_polyfitter.py --from-trouble --namecode 260526_PJM --apps MeasuredEHF \\
        --as-trial-model --run-so --skip-jr
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ts_paths  # noqa: E402,F401

from wrap_detect_lib import detect_length_jumps, import_opensim  # noqa: E402
from wrap_fbp_lib import _log, _remove_quiet, _run_full_so  # noqa: E402
from wrap_ppf_lib import (  # noqa: E402
    DEFAULT_MUSCLES,
    PPF_DEFAULTS,
    build_ppf_sidecar,
    case_paths,
    write_validation,
)
from DETECT_muscle_path_wrap_jump import resolve_paths, trouble_cases  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-trouble", action="store_true", required=True)
    parser.add_argument("--namecode", default=None)
    parser.add_argument("--condition", default=None)
    parser.add_argument("--seg", default=None)
    parser.add_argument("--apps", default="")
    parser.add_argument("--muscles", default=",".join(DEFAULT_MUSCLES),
                        help="Muscles to refit. 'jumped' = muscles with IK length jumps.")
    parser.add_argument("--max-order", type=int, default=PPF_DEFAULTS["max_order"])
    parser.add_argument("--samples-per-frame", type=int, default=PPF_DEFAULTS["samples_per_frame"])
    parser.add_argument("--bounds-deg", type=float, default=PPF_DEFAULTS["global_bounds_deg"],
                        help="Sampling offset ± around IK values (deg).")
    parser.add_argument("--frame-stride", type=int, default=PPF_DEFAULTS["frame_stride"])
    parser.add_argument("--parallel", type=int, default=PPF_DEFAULTS["parallel"])
    parser.add_argument("--no-stepwise", action="store_true")
    parser.add_argument("--as-trial-model", action="store_true",
                        help="Write to the pipeline trial-model name (_WrapFBP.osim).")
    parser.add_argument("--run-so", action="store_true")
    parser.add_argument("--skip-jr", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    segs = {s.strip() for s in args.seg.split(",") if s.strip()} if args.seg else None
    apps = {a.strip() for a in args.apps.split(",") if a.strip()} if args.apps else None
    cases = trouble_cases(namecode=args.namecode, condition=args.condition,
                          segments=segs, apps=apps)
    if not cases:
        _log("No SO trouble cases matched.")
        return
    try:
        osim = import_opensim()
    except ImportError as exc:
        raise SystemExit(
            "opensim is not importable in this interpreter. "
            "Use the conda env `osim` (OpenSim >= 4.5)."
        ) from exc
    if not hasattr(osim, "PolynomialPathFitter"):
        raise SystemExit("opensim.PolynomialPathFitter missing (needs OpenSim >= 4.5).")

    opts = dict(
        max_order=args.max_order,
        samples_per_frame=args.samples_per_frame,
        global_bounds_deg=args.bounds_deg,
        frame_stride=args.frame_stride,
        parallel=args.parallel,
        stepwise=not args.no_stepwise,
    )
    timeout = None if args.timeout_s <= 0 else args.timeout_s
    fixed = [m.strip() for m in args.muscles.split(",") if m.strip() and m.strip() != "jumped"]

    for k, case in enumerate(cases, start=1):
        tag = f"[{k}/{len(cases)}] {case['namecode']} {case['condition']} {case['segment']} {case['app']}"
        model, ik = resolve_paths(case)
        base = os.path.basename(model)
        if "_Wrap" in base or "_ChestPatch" in base:
            _log(f"{tag} SKIP source is already a trial model: {base}")
            continue
        islands, jumped = detect_length_jumps(osim, model, ik)
        muscles = fixed or jumped
        _log(f"{tag} islands={len(islands)} jumped={jumped} fit={muscles}")
        if not muscles or args.dry_run:
            continue
        out = case_paths(case, as_trial_model=args.as_trial_model)
        try:
            built, info = build_ppf_sidecar(model_path=model, ik_path=ik, islands=islands,
                                            muscles=muscles, out_osim=out, opts=opts)
        except Exception as exc:  # noqa: BLE001
            _log(f"[FAIL] {tag}: {exc}")
            continue
        if not built:
            continue
        info["source_model"] = model
        info["ik"] = ik
        if args.run_so:
            try:
                _run_full_so(case, built, skip_jr=args.skip_jr, timeout_s=timeout)
                info["so_status"] = "ok"
            except Exception as exc:  # noqa: BLE001
                _log(f"[PPF] SO failed: {exc}")
                info["so_status"] = f"error: {exc}"
                if args.as_trial_model:
                    _remove_quiet(built)
        write_validation(built, {kk: case[kk] for kk in ("namecode", "condition", "segment", "app")}, info)


if __name__ == "__main__":
    main()

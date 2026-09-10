import argparse
import os
import sys


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.append(CODES_DIR)

from SUB_Info import subjects
from PATH_RULE import ResultPaths
from opensim_pipeline_handlers import (
    prepare_bk_setup,
    prepare_extload_setup,
    prepare_jr_setup,
    prepare_so_setup,
    run_bk,
    run_ik,
    run_jr,
    run_so,
)
from pipeline_rules import (
    jr_suffixes,
    resolve_model_path,
)


VALID_TOOLS: tuple[str, ...] = ("extload", "ik", "so", "bk", "jr")


def _log(msg: str) -> None:
    """Print and flush immediately so Jupyter / subprocess streaming can show progress."""
    print(msg, flush=True)


def _parse_tools(raw_tools: str) -> list[str]:
    tools = [t.strip().lower() for t in raw_tools.split(",") if t.strip()]
    unknown = [t for t in tools if t not in VALID_TOOLS]
    if unknown:
        raise ValueError(
            f"Unknown tool(s): {unknown}. Valid tools: {list(VALID_TOOLS)}"
        )
    # Preserve canonical execution order regardless of user input order.
    return [t for t in VALID_TOOLS if t in tools]


def _pick_namecode(raw: str | None) -> str:
    if raw:
        if raw not in subjects:
            raise KeyError(f"Unknown namecode: {raw}")
        return raw
    return next(iter(subjects.keys()))


def _pick_condition(namecode: str, raw: str | None) -> str:
    cond_keys = list(subjects[namecode]["conditions"].keys())
    if raw:
        if raw not in cond_keys:
            raise KeyError(f"Unknown condition: {raw}. Available: {cond_keys}")
        return raw
    return cond_keys[0]


def _pick_apps(cp, raw_apps: str | None) -> list[str]:
    if raw_apps:
        selected = [a.strip() for a in raw_apps.split(",") if a.strip()]
        unknown = [a for a in selected if a not in cp.apps]
        if unknown:
            raise ValueError(f"Unknown apps: {unknown}. Available: {cp.apps}")
        return selected
    return list(cp.apps)


def _pick_segments(cp, raw_segments: str | None) -> list[str]:
    # PATH_RULE currently exposes this list as all_sections() but values are segment labels (e.g., 1AB, 1BC).
    all_segments = cp.all_sections()
    if raw_segments:
        selected = [s.strip() for s in raw_segments.split(",") if s.strip()]
        unknown = [s for s in selected if s not in all_segments]
        if unknown:
            raise ValueError(f"Unknown segments: {unknown}. Available sample: {all_segments[:10]}")
        return selected
    return all_segments


def _print_structure_validation_sample(rp, cp, apps: list[str],
                                       segments: list[str]) -> None:
    sample_seg = segments[0]
    sample_app = apps[0]
    sample_section = cp.seg_to_section(sample_seg)
    sample_ik_model = resolve_model_path(rp, cp.cond, sample_app, "ik",
                                         must_exist=False)
    sample_so_model = resolve_model_path(rp, cp.cond, sample_app, "so",
                                         must_exist=False)
    sample_jr_model = resolve_model_path(rp, cp.cond, sample_app, "jr",
                                         must_exist=False)
    print("\n[Structure Validation - Sample]", flush=True)
    print(f"  condition   : {cp.cond}", flush=True)
    print(f"  section     : {sample_section}", flush=True)
    print(f"  segment     : {sample_seg}", flush=True)
    print(f"  app         : {sample_app}", flush=True)
    print(f"  markers     : {cp.markers_dir(sample_section)}", flush=True)
    print(f"  extload dir : {cp.extload_dir(sample_section)}", flush=True)
    print(f"  ik dir      : {cp.ik_dir(sample_section)}", flush=True)
    print(f"  bk dir      : {cp.bk_dir(sample_section)}", flush=True)
    print(f"  so dir      : {cp.so_dir(sample_section, sample_app)}", flush=True)
    print(f"  jr dir      : {cp.jr_dir(sample_section, sample_app)}", flush=True)
    print(f"  trc_path    : {cp.trc_path(sample_seg)}", flush=True)
    print(f"  ext_xml     : {cp.setup_extload_path(sample_seg, sample_app)}", flush=True)
    print(f"  ik_xml      : {cp.setup_ik_path(sample_seg)}", flush=True)
    print(f"  bk_xml      : {cp.setup_bk_path(sample_seg)}", flush=True)
    print(f"  so_xml      : {cp.setup_so_path(sample_seg, sample_app)}", flush=True)
    for sfx in jr_suffixes(sample_app):
        tag = sfx if sfx else "child"
        print(f"  jr_xml[{tag}] : {cp.setup_jr_path(sample_seg, sample_app, sfx)}",
              flush=True)
    print(f"  model(ik)   : {os.path.basename(sample_ik_model)}", flush=True)
    print(f"  model(so)   : {os.path.basename(sample_so_model)}", flush=True)
    print(f"  model(jr)   : {os.path.basename(sample_jr_model)}", flush=True)
    print( "  (reserve/residual/torque actuators are baked into the above "
           "osim files by Codes/b_Build_Model/add_reserve_actuators.py)",
           flush=True)


def _run_extload(*, cp, seg, app, args):
    _log(f"[RUN ] seg={seg}  tool=extload  app={app}")
    ext_path = prepare_extload_setup(
        cp=cp, seg=seg, app=app,
        extload_template_path=args.extload_template,
        dry_run=args.dry_run,
    )
    _log(f"[DONE] seg={seg}  tool=extload  app={app}  -> {ext_path}")


def _run_ik(*, cp, rp, seg, app, args, condition):
    ik_model = resolve_model_path(rp, condition, app, "ik",
                                  must_exist=not args.dry_run)
    _log(f"[RUN ] seg={seg}  tool=ik  app={app}  "
         f"model={os.path.basename(ik_model)}")
    ik_path = run_ik(
        cp=cp, rp=rp, seg=seg, app=app,
        ik_template_default=args.ik_template_default,
        ik_template_addbox=args.ik_template_addbox,
        dry_run=args.dry_run,
    )
    _log(f"[DONE] seg={seg}  tool=ik  app={app}  -> {ik_path}")


def _run_so(*, cp, rp, seg, app, args, condition):
    so_model = resolve_model_path(rp, condition, app, "so",
                                  must_exist=not args.dry_run)
    _log(f"[RUN ] seg={seg}  tool=so  app={app}  "
         f"model={os.path.basename(so_model)}")
    so_xml = prepare_so_setup(cp=cp, rp=rp, seg=seg, app=app,
                              dry_run=args.dry_run)
    _log(f"[OK  ] seg={seg}  tool=so  app={app}  setup={so_xml}")
    if args.no_run_so or args.dry_run:
        _log(f"[DONE] seg={seg}  tool=so  app={app}  "
             f"(setup only; run skipped)")
        return
    # RUN is dispatched to a fresh subprocess (see opensim_pipeline_handlers
    # module docstring) — required to avoid the OpenSim SET+RUN in-process
    # silent-skip bug that the OLD pipeline worked around by splitting
    # ``*_SET.py`` and ``*_RUN.py`` into separate files.
    run_so(cp=cp, rp=rp, seg=seg, app=app, dry_run=False)
    _log(f"[DONE] seg={seg}  tool=so  app={app}  "
         f"-> {cp.so_dir(cp.seg_to_section(seg), app)}")


def _run_bk(*, cp, rp, seg, args):
    _log(f"[RUN ] seg={seg}  tool=bk  "
         f"model={os.path.basename(rp.model_path(''))}")
    bk_xml = prepare_bk_setup(cp=cp, rp=rp, seg=seg,
                              bk_ik_app=args.bk_ik_app,
                              dry_run=args.dry_run)
    _log(f"[OK  ] seg={seg}  tool=bk  setup={bk_xml}")
    if args.no_run_bk or args.dry_run:
        _log(f"[DONE] seg={seg}  tool=bk  (setup only; run skipped)")
        return
    run_bk(cp=cp, rp=rp, seg=seg, dry_run=False)
    _log(f"[DONE] seg={seg}  tool=bk  "
         f"-> {cp.bk_dir(cp.seg_to_section(seg))}")


def _run_jr(*, cp, rp, seg, app, args, condition):
    jr_model = resolve_model_path(rp, condition, app, "jr",
                                  must_exist=not args.dry_run)
    _log(f"[RUN ] seg={seg}  tool=jr  app={app}  "
         f"model={os.path.basename(jr_model)}")
    jr_xmls = prepare_jr_setup(cp=cp, rp=rp, seg=seg, app=app,
                               dry_run=args.dry_run)
    for x in jr_xmls:
        _log(f"[OK  ] seg={seg}  tool=jr  app={app}  setup={x}")
    if args.no_run_jr or args.dry_run:
        _log(f"[DONE] seg={seg}  tool=jr  app={app}  "
             f"(setup only; run skipped)")
        return
    # RUN dispatched to a fresh subprocess (see opensim_pipeline_handlers).
    run_jr(cp=cp, rp=rp, seg=seg, app=app, dry_run=False)
    _log(f"[DONE] seg={seg}  tool=jr  app={app}  "
         f"-> {cp.jr_dir(cp.seg_to_section(seg), app)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenSim pipeline (ExtLoad / IK / SO / BK / JR)"
    )
    parser.add_argument("--namecode", default=None, help="Subject namecode key from SUB_Info.subjects")
    parser.add_argument("--condition", default=None, help="Condition key in the selected subject")
    parser.add_argument(
        "--tools", default="extload,ik",
        help=f"Comma-separated subset of {list(VALID_TOOLS)} "
             "(execution order is fixed regardless of input order)",
    )
    parser.add_argument("--apps", default=None, help="Comma-separated app names; default is all protocol apps")
    parser.add_argument("--segments", default=None, help="Comma-separated segment labels (e.g., 1AB,1BC,1CA)")
    # Backward-compat alias in case old cells still use --sections.
    parser.add_argument("--sections", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="No file execution; only print planned actions")
    parser.add_argument(
        "--extload-template",
        default=r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\SETUP_ExtLoad.xml",
        help="Template XML path for ExtLoad setup generation",
    )
    parser.add_argument(
        "--ik-template-default",
        default=r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\SETUP_IK_APP1,2.xml",
        help="Default IK template path",
    )
    parser.add_argument(
        "--ik-template-addbox",
        default=r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\SETUP_IK_APP3,4.xml",
        help="IK template path for AddBox-like model",
    )
    parser.add_argument(
        "--bk-ik-app", default="MeasuredEHF",
        help="Which app's IK / ExtLoad to bind into the (segment-level) BK setup "
             "(default: MeasuredEHF — kinematics-only, mass-independent)",
    )
    parser.add_argument("--no-run-so", action="store_true",
                        help="Only write SO setup XMLs, do not execute the tool")
    parser.add_argument("--no-run-bk", action="store_true",
                        help="Only write BK setup XMLs, do not execute the tool")
    parser.add_argument("--no-run-jr", action="store_true",
                        help="Only write JR setup XMLs, do not execute the tool")
    args = parser.parse_args()

    namecode = _pick_namecode(args.namecode)
    rp = ResultPaths(namecode)
    condition = _pick_condition(namecode, args.condition)
    cp = rp.for_condition(condition)
    tools = _parse_tools(args.tools)
    apps = _pick_apps(cp, args.apps)
    raw_segments = args.segments if args.segments is not None else args.sections
    segments = _pick_segments(cp, raw_segments)
    error_log = set(cp.error_log or [])

    cp.build_tree()

    _log("[OpenSim Pipeline]")
    _log(f"  namecode  : {namecode}")
    _log(f"  subject   : {rp.sub_label}")
    _log(f"  protocol  : {rp.protocol}")
    _log(f"  condition : {condition}")
    _log(f"  tools     : {tools}")
    _log(f"  apps      : {apps}")
    _log(f"  dry_run   : {args.dry_run}")
    _log(f"  segments  : {len(segments)} selected")
    if error_log:
        _log(f"  error_log : {sorted(error_log)}")

    _print_structure_validation_sample(rp, cp, apps, segments)

    n_seg = len(segments)
    for i_seg, seg in enumerate(segments, start=1):
        if seg in error_log:
            _log(f"[SKIP] ({i_seg}/{n_seg}) seg={seg} (in error_log)")
            continue

        _log(f"\n===== ({i_seg}/{n_seg}) seg={seg}  START =====")
        for app in apps:
            if "extload" in tools:
                _run_extload(cp=cp, seg=seg, app=app, args=args)

            if "ik" in tools:
                _run_ik(cp=cp, rp=rp, seg=seg, app=app,
                        args=args, condition=condition)

            if "so" in tools:
                _run_so(cp=cp, rp=rp, seg=seg, app=app,
                        args=args, condition=condition)

            if "jr" in tools:
                _run_jr(cp=cp, rp=rp, seg=seg, app=app,
                        args=args, condition=condition)

        if "bk" in tools:
            _run_bk(cp=cp, rp=rp, seg=seg, args=args)

        _log(f"===== ({i_seg}/{n_seg}) seg={seg}  COMPLETE =====")

    _log("\n[OpenSim Pipeline] ALL REQUESTED WORK COMPLETE")


if __name__ == "__main__":
    main()

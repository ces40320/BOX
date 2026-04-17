import argparse
import os
import sys


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.append(CODES_DIR)

from SUB_Info import subjects
from PATH_RULE import ResultPaths
from opensim_pipeline_handlers import prepare_extload_setup, run_ik
from pipeline_rules import resolve_model_path


def _parse_tools(raw_tools: str) -> list[str]:
    tools = [t.strip().lower() for t in raw_tools.split(",") if t.strip()]
    valid = {"extload", "ik"}
    unknown = [t for t in tools if t not in valid]
    if unknown:
        raise ValueError(f"Unknown tool(s): {unknown}. Valid tools: {sorted(valid)}")
    return tools


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
    sample_model = resolve_model_path(rp, cp.cond, sample_app, "ik",
                                      must_exist=False)
    print("\n[Structure Validation - Sample]")
    print(f"  condition : {cp.cond}")
    print(f"  section   : {sample_section}")
    print(f"  segment   : {sample_seg}")
    print(f"  app       : {sample_app}")
    print(f"  markers   : {cp.markers_dir(sample_section)}")
    print(f"  extload   : {cp.extload_dir(sample_section)}")
    print(f"  ik        : {cp.ik_dir(sample_section)}")
    print(f"  trc_path  : {cp.trc_path(sample_seg)}")
    print(f"  ext_xml   : {cp.setup_extload_path(sample_seg, sample_app)}")
    print(f"  ik_xml    : {cp.setup_ik_path(sample_seg)}")
    print(f"  model(ik) : {os.path.basename(sample_model)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSim pipeline (ExtLoad + IK first stage)")
    parser.add_argument("--namecode", default=None, help="Subject namecode key from SUB_Info.subjects")
    parser.add_argument("--condition", default=None, help="Condition key in the selected subject")
    parser.add_argument("--tools", default="extload,ik", help="Comma-separated: extload,ik")
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

    print("[OpenSim Pipeline]")
    print(f"  namecode  : {namecode}")
    print(f"  subject   : {rp.sub_label}")
    print(f"  protocol  : {rp.protocol}")
    print(f"  condition : {condition}")
    print(f"  tools     : {tools}")
    print(f"  apps      : {apps}")
    print(f"  dry_run   : {args.dry_run}")
    print(f"  segments  : {len(segments)} selected")
    if error_log:
        print(f"  error_log : {sorted(error_log)}")

    _print_structure_validation_sample(rp, cp, apps, segments)

    for seg in segments:
        if seg in error_log:
            print(f"[SKIP] {seg} (in error_log)")
            continue

        for app in apps:
            if "extload" in tools:
                ext_path = prepare_extload_setup(
                    cp=cp,
                    seg=seg,
                    app=app,
                    extload_template_path=args.extload_template,
                    dry_run=args.dry_run,
                )
                print(f"[OK] ExtLoad setup: {ext_path}")

            if "ik" in tools:
                ik_model = resolve_model_path(
                    rp, condition, app, "ik",
                    must_exist=not args.dry_run,
                )
                print(f"[MODEL] cond={condition} app={app} stage=ik "
                      f"-> {os.path.basename(ik_model)}")
                ik_path = run_ik(
                    cp=cp,
                    rp=rp,
                    seg=seg,
                    app=app,
                    ik_template_default=args.ik_template_default,
                    ik_template_addbox=args.ik_template_addbox,
                    dry_run=args.dry_run,
                )
                print(f"[OK] IK setup/run: {ik_path}")


if __name__ == "__main__":
    main()

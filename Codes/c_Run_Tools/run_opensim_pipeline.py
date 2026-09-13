import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from types import SimpleNamespace


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CODES_DIR = os.path.dirname(THIS_DIR)
if CODES_DIR not in sys.path:
    sys.path.append(CODES_DIR)

from SUB_Info import subjects
from PATH_RULE import ResultPaths
from opensim_pipeline_handlers import (
    prepare_bk_setup,
    prepare_extload_setup,
    prepare_id_setup,
    prepare_jr_setup,
    prepare_so_setup,
    run_bk,
    run_id,
    run_ik,
    run_jr,
    run_so,
)
from pipeline_rules import (
    DEFAULT_ANALYZE_TIMEOUT_S,
    ID_APP,
    ik_suffix,
    jr_suffixes,
    resolve_model_path,
)
from update_pipeline_progress import (
    prune_resolved_troubles,
    record_trouble,
    refresh_progress_sheet,
    sub_number_for_namecode,
)


VALID_TOOLS: tuple[str, ...] = ("extload", "ik", "id", "so", "bk", "jr")
# Tools that iterate the selected app list. ID is excluded — HeavyHand only.
_APP_LOOP_TOOLS: tuple[str, ...] = ("extload", "ik", "so", "jr")


def _log(msg: str) -> None:
    """Print and flush immediately so Jupyter / subprocess streaming can show progress."""
    print(msg, flush=True)


def _parse_csv(raw: str | None) -> list[str] | None:
    """Comma-separated tokens, or None when the flag was omitted (→ full list)."""
    if raw is None:
        return None
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_tools(raw_tools: str) -> list[str]:
    tools = [t.strip().lower() for t in raw_tools.split(",") if t.strip()]
    unknown = [t for t in tools if t not in VALID_TOOLS]
    if unknown:
        raise ValueError(
            f"Unknown tool(s): {unknown}. Valid tools: {list(VALID_TOOLS)}"
        )
    # Preserve canonical execution order regardless of user input order.
    return [t for t in VALID_TOOLS if t in tools]


def _pick_namecodes(raw: str | None) -> list[str]:
    """Resolve --namecode. Omitted → all SUB_Info subjects (dict order)."""
    all_codes = list(subjects.keys())
    selected = _parse_csv(raw)
    if selected is None:
        return all_codes
    unknown = [c for c in selected if c not in subjects]
    if unknown:
        raise KeyError(
            f"Unknown namecode(s): {unknown}. Available: {all_codes}"
        )
    return selected


def _pick_conditions(namecode: str, raw: str | None) -> list[str]:
    """Resolve --condition for one subject. Omitted → all of that subject's conditions."""
    cond_keys = list(subjects[namecode]["conditions"].keys())
    selected = _parse_csv(raw)
    if selected is None:
        return cond_keys
    unknown = [c for c in selected if c not in cond_keys]
    if unknown:
        raise KeyError(
            f"Unknown condition(s) for {namecode}: {unknown}. "
            f"Available: {cond_keys}"
        )
    return selected


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


def _run_flags_from_args(args) -> dict:
    """Plain dict for spawn-safe worker payloads (no argparse.Namespace)."""
    return {
        "dry_run": bool(args.dry_run),
        "skip_existing": bool(args.skip_existing),
        "extload_template": args.extload_template,
        "ik_template_default": args.ik_template_default,
        "ik_template_addbox": args.ik_template_addbox,
        "bk_ik_app": args.bk_ik_app,
        "no_run_so": bool(args.no_run_so),
        "no_run_bk": bool(args.no_run_bk),
        "no_run_jr": bool(args.no_run_jr),
        "no_run_id": bool(args.no_run_id),
        "tool_timeout": args.tool_timeout,
    }


def _canonical_result_paths(cp, seg: str, tool: str, app: str | None) -> list[str]:
    """Paths that must exist for ``--skip-existing`` to skip this tool step.

    For analyze tools this is the canonical ``.mot`` / ``.sto`` output.
    ExtLoad is special: this pipeline only *writes* the SETUP XML (the
    ``.mot`` is experimental input from ``a_Get_Exp_Data``). Skipping when
    the ``.mot`` exists would leave SO/JR pointing at a missing ExtLoad
    SETUP and cause mass AnalyzeTool failures — so ExtLoad skips on the
    SETUP XML instead.
    """
    tool = tool.lower()
    if tool == "extload":
        if app is None:
            raise ValueError("extload requires app")
        return [cp.setup_extload_path(seg, app)]
    if tool == "ik":
        if app is None:
            raise ValueError("ik requires app")
        return [cp.ik_path(seg, ik_suffix(app))]
    if tool == "id":
        if app is None:
            raise ValueError("id requires app")
        return [cp.id_path(seg, app)]
    if tool == "so":
        if app is None:
            raise ValueError("so requires app")
        return [cp.so_path(seg, app, "force")]
    if tool == "bk":
        return [cp.bk_path(seg, "pos_global")]
    if tool == "jr":
        if app is None:
            raise ValueError("jr requires app")
        return [cp.jr_path(seg, app, sfx) for sfx in jr_suffixes(app)]
    raise ValueError(f"Unknown tool for skip check: {tool!r}")


def _try_skip_existing(*, cp, seg: str, tool: str, app: str | None,
                       args) -> bool:
    """If ``--skip-existing`` and all canonical results exist, log and return True."""
    if not getattr(args, "skip_existing", False):
        return False
    paths = _canonical_result_paths(cp, seg, tool, app)
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        return False
    app_tag = f"  app={app}" if app is not None else ""
    shown = ", ".join(os.path.basename(p) for p in paths)
    _log(f"[SKIP] seg={seg}  tool={tool}{app_tag}  "
         f"(exists: {shown})")
    return True


def _resolve_workers(requested: int, n_tasks: int) -> int:
    """``0`` → cpu_count; always clamp to ``[1, n_tasks]``."""
    if n_tasks <= 0:
        return 1
    if requested == 0:
        requested = os.cpu_count() or 1
    return max(1, min(int(requested), n_tasks))


def _print_structure_validation_sample(rp, cp, apps: list[str],
                                       segments: list[str]) -> None:
    sample_seg = segments[0]
    sample_app = apps[0]
    sample_section = cp.seg_to_section(sample_seg)
    sample_ik_model = resolve_model_path(rp, cp.cond, sample_app, "ik",
                                         must_exist=False)
    sample_id_model = resolve_model_path(rp, cp.cond, ID_APP, "id",
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
    print(f"  id dir      : {cp.id_dir(sample_section, ID_APP)}  "
          f"(HeavyHand only)", flush=True)
    print(f"  bk dir      : {cp.bk_dir(sample_section)}", flush=True)
    print(f"  so dir      : {cp.so_dir(sample_section, sample_app)}", flush=True)
    print(f"  jr dir      : {cp.jr_dir(sample_section, sample_app)}", flush=True)
    print(f"  trc_path    : {cp.trc_path(sample_seg)}", flush=True)
    print(f"  ext_xml     : {cp.setup_extload_path(sample_seg, sample_app)}", flush=True)
    print(f"  ik_xml      : {cp.setup_ik_path(sample_seg)}", flush=True)
    print(f"  id_xml      : {cp.setup_id_path(sample_seg, ID_APP)}  "
          f"(HeavyHand only)", flush=True)
    print(f"  bk_xml      : {cp.setup_bk_path(sample_seg)}", flush=True)
    print(f"  so_xml      : {cp.setup_so_path(sample_seg, sample_app)}", flush=True)
    for sfx in jr_suffixes(sample_app):
        tag = sfx if sfx else "child"
        print(f"  jr_xml[{tag}] : {cp.setup_jr_path(sample_seg, sample_app, sfx)}",
              flush=True)
    print(f"  model(ik)   : {os.path.basename(sample_ik_model)}", flush=True)
    print(f"  model(id)   : {os.path.basename(sample_id_model)}  "
          f"({ID_APP})", flush=True)
    print(f"  model(so)   : {os.path.basename(sample_so_model)}", flush=True)
    print(f"  model(jr)   : {os.path.basename(sample_jr_model)}", flush=True)
    print( "  (reserve/residual/torque actuators are baked into the above "
           "osim files by Codes/b_Build_Model/add_reserve_actuators.py)",
           flush=True)


def _run_extload(*, cp, seg, app, args):
    if _try_skip_existing(cp=cp, seg=seg, tool="extload", app=app, args=args):
        return
    _log(f"[RUN ] seg={seg}  tool=extload  app={app}")
    ext_path = prepare_extload_setup(
        cp=cp, seg=seg, app=app,
        extload_template_path=args.extload_template,
        dry_run=args.dry_run,
    )
    _log(f"[DONE] seg={seg}  tool=extload  app={app}  -> {ext_path}")


def _run_ik(*, cp, rp, seg, app, args, condition):
    if _try_skip_existing(cp=cp, seg=seg, tool="ik", app=app, args=args):
        return
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


def _run_id(*, cp, rp, seg, app, args, condition):
    if _try_skip_existing(cp=cp, seg=seg, tool="id", app=app, args=args):
        return
    id_model = resolve_model_path(rp, condition, app, "id",
                                  must_exist=not args.dry_run)
    _log(f"[RUN ] seg={seg}  tool=id  app={app}  "
         f"model={os.path.basename(id_model)}")
    id_xml = prepare_id_setup(cp=cp, rp=rp, seg=seg, app=app,
                              dry_run=args.dry_run)
    _log(f"[OK  ] seg={seg}  tool=id  app={app}  setup={id_xml}")
    if args.no_run_id or args.dry_run:
        _log(f"[DONE] seg={seg}  tool=id  app={app}  "
             f"(setup only; run skipped)")
        return
    id_sto = run_id(cp=cp, rp=rp, seg=seg, app=app, dry_run=False)
    _log(f"[DONE] seg={seg}  tool=id  app={app}  -> {id_sto}")


def _run_so(*, cp, rp, seg, app, args, condition):
    if _try_skip_existing(cp=cp, seg=seg, tool="so", app=app, args=args):
        return
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
    run_so(cp=cp, rp=rp, seg=seg, app=app, dry_run=False,
           timeout_s=args.tool_timeout)
    _log(f"[DONE] seg={seg}  tool=so  app={app}  "
         f"-> {cp.so_dir(cp.seg_to_section(seg), app)}")


def _run_bk(*, cp, rp, seg, args):
    if _try_skip_existing(cp=cp, seg=seg, tool="bk", app=None, args=args):
        return
    _log(f"[RUN ] seg={seg}  tool=bk  "
         f"model={os.path.basename(rp.model_path(''))}")
    bk_xml = prepare_bk_setup(cp=cp, rp=rp, seg=seg,
                              bk_ik_app=args.bk_ik_app,
                              dry_run=args.dry_run)
    _log(f"[OK  ] seg={seg}  tool=bk  setup={bk_xml}")
    if args.no_run_bk or args.dry_run:
        _log(f"[DONE] seg={seg}  tool=bk  (setup only; run skipped)")
        return
    run_bk(cp=cp, rp=rp, seg=seg, dry_run=False,
           timeout_s=args.tool_timeout)
    _log(f"[DONE] seg={seg}  tool=bk  "
         f"-> {cp.bk_dir(cp.seg_to_section(seg))}")


def _run_jr(*, cp, rp, seg, app, args, condition):
    if _try_skip_existing(cp=cp, seg=seg, tool="jr", app=app, args=args):
        return
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
    run_jr(cp=cp, rp=rp, seg=seg, app=app, dry_run=False,
           timeout_s=args.tool_timeout)
    _log(f"[DONE] seg={seg}  tool=jr  app={app}  "
         f"-> {cp.jr_dir(cp.seg_to_section(seg), app)}")


def _fail_result(
    seg: str,
    tool: str,
    app: str | None,
    exc: BaseException,
    *,
    condition: str,
) -> dict:
    freeze = getattr(exc, "freeze_sim_time", None)
    out = {
        "ok": False,
        "seg": seg,
        "condition": condition,
        "tool": tool,
        "app": app if app is not None else "(shared)",
        "error": f"{type(exc).__name__}: {exc}",
    }
    if freeze is not None:
        out["freeze_sim_time"] = float(freeze)
    return out


def _run_one_segment(
    namecode: str,
    condition: str,
    seg: str,
    tools: list[str],
    apps: list[str],
    run_flags: dict,
) -> dict:
    """Run all selected tools for one segment. Spawn-safe top-level worker.

    Returns ``{"ok": True, "seg": ..., "condition": ...}`` or a structured
    failure dict. Worker process should exit after this returns
    (``max_tasks_per_child=1``) so OpenSim native memory is reclaimed by
    the OS.
    """
    args = SimpleNamespace(**run_flags)
    try:
        rp = ResultPaths(namecode)
        cp = rp.for_condition(condition)

        # App loop only when a selected tool actually varies by app.
        # ID is not in this loop — it runs once for HeavyHand below.
        if any(t in tools for t in _APP_LOOP_TOOLS):
            for app in apps:
                if "extload" in tools:
                    try:
                        _run_extload(cp=cp, seg=seg, app=app, args=args)
                    except Exception as exc:
                        return _fail_result(
                            seg, "extload", app, exc, condition=condition,
                        )

                if "ik" in tools:
                    try:
                        _run_ik(cp=cp, rp=rp, seg=seg, app=app,
                                args=args, condition=condition)
                    except Exception as exc:
                        return _fail_result(
                            seg, "ik", app, exc, condition=condition,
                        )

                if "so" in tools:
                    try:
                        _run_so(cp=cp, rp=rp, seg=seg, app=app,
                                args=args, condition=condition)
                    except Exception as exc:
                        return _fail_result(
                            seg, "so", app, exc, condition=condition,
                        )

                if "jr" in tools:
                    try:
                        _run_jr(cp=cp, rp=rp, seg=seg, app=app,
                                args=args, condition=condition)
                    except Exception as exc:
                        return _fail_result(
                            seg, "jr", app, exc, condition=condition,
                        )

        if "id" in tools and ID_APP in apps:
            try:
                _run_id(cp=cp, rp=rp, seg=seg, app=ID_APP,
                        args=args, condition=condition)
            except Exception as exc:
                return _fail_result(
                    seg, "id", ID_APP, exc, condition=condition,
                )

        if "bk" in tools:
            try:
                _run_bk(cp=cp, rp=rp, seg=seg, args=args)
            except Exception as exc:
                return _fail_result(
                    seg, "bk", "(shared)", exc, condition=condition,
                )

        return {"ok": True, "seg": seg, "condition": condition}
    except Exception as exc:
        return _fail_result(seg, "setup", None, exc, condition=condition)


def _handle_segment_result(
    *,
    namecode: str,
    condition: str,
    result: dict,
    update_trouble_sheet: bool,
    dry_run: bool,
) -> bool:
    """Log result; record trouble if failed. Returns True if ok."""
    seg = result.get("seg", "?")
    if result.get("ok"):
        _log(f"[OK  ] condition={condition}  seg={seg}")
        return True

    tool = result.get("tool", "?")
    app = result.get("app", "(shared)")
    err = result.get("error", "")
    freeze = result.get("freeze_sim_time")
    freeze_txt = (
        f"  freeze_sim_time_s={float(freeze):.6g}"
        if freeze is not None
        else ""
    )
    _log(
        f"[FAIL] condition={condition}  seg={seg}  "
        f"tool={tool}  app={app}{freeze_txt}  {err}"
    )

    if dry_run or not update_trouble_sheet:
        return False

    try:
        entry = record_trouble(
            namecode=namecode,
            condition=condition,
            segment=seg,
            tool=str(tool),
            app=str(app),
            error=str(err),
            freeze_sim_time=(
                float(freeze) if freeze is not None else None
            ),
        )
        freeze_mark = (
            f"  freeze_sim_time_s={entry['freeze_sim_time']}"
            if "freeze_sim_time" in entry
            else ""
        )
        _log(
            f"[TROUBLE] recorded  section={entry['section']}  "
            f"tool={entry['tool']}  app={entry['app']}  "
            f"seg={entry['segment']}  mark=☒{freeze_mark}"
        )
    except Exception as exc:
        _log(f"[TROUBLE] failed to record: {type(exc).__name__}: {exc}")
    return False


def _collect_subject_work(
    *,
    namecode: str,
    conditions: list[str],
    tools: list[str],
    args,
    raw_apps: str | None,
    raw_segments: str | None,
) -> list[tuple[str, str, list[str]]]:
    """Prepare trees and return ``(condition, seg, apps)`` tasks for one subject.

    Workers share one pool across all conditions of this subject so a free
    worker can start the next condition's trial without waiting for the
    current condition to drain.
    """
    rp = ResultPaths(namecode)
    run_app_loop = any(t in tools for t in _APP_LOOP_TOOLS)
    run_bk = "bk" in tools
    work: list[tuple[str, str, list[str]]] = []

    _log("\n" + "=" * 60)
    _log("[OpenSim Pipeline]")
    _log(f"  namecode  : {namecode}")
    _log(f"  subject   : {rp.sub_label}")
    _log(f"  protocol  : {rp.protocol}")
    _log(f"  conditions: {conditions}")
    _log(f"  tools     : {tools}")
    _log(f"  dry_run   : {args.dry_run}")
    _log(f"  skip_existing : {args.skip_existing}")
    _log(f"  tool_timeout : {args.tool_timeout}  "
         f"(log-stall interval; None = disabled)")

    for condition in conditions:
        cp = rp.for_condition(condition)
        apps = _pick_apps(cp, raw_apps)
        segments = _pick_segments(cp, raw_segments)
        error_log = set(cp.error_log or [])
        cp.build_tree()

        _log(f"\n--- condition={condition} ---")
        _log(f"  apps      : {apps}")
        if "id" in tools:
            if ID_APP in apps:
                _log(f"  id        : {ID_APP} only (not looped over other apps)")
            else:
                _log(f"  id        : skipped ({ID_APP} not in selected apps)")
        _log(f"  segments  : {len(segments)} selected")
        if error_log:
            _log(f"  error_log : {sorted(error_log)}")

        runnable = [s for s in segments if s not in error_log]
        for seg in segments:
            if seg in error_log:
                _log(f"[SKIP] condition={condition}  seg={seg} (in error_log)")

        run_id = "id" in tools and ID_APP in apps
        if not runnable:
            _log(f"[OpenSim Pipeline] skip {namecode} / {condition}  (no segments)")
            continue
        if not (run_app_loop or run_id or run_bk):
            _log(
                f"[OpenSim Pipeline] skip {namecode} / {condition}  "
                f"(no selected tool applies to apps={apps})"
            )
            continue

        _print_structure_validation_sample(rp, cp, apps, runnable)
        for seg in runnable:
            work.append((condition, seg, apps))

    return work


def _run_one_subject(
    *,
    namecode: str,
    conditions: list[str],
    tools: list[str],
    args,
    raw_apps: str | None,
    raw_segments: str | None,
) -> list[dict]:
    """Run all conditions for one subject with a shared segment worker pool.

    Returns the list of failed segment result dicts (empty if all ok).
    """
    run_flags = _run_flags_from_args(args)
    work = _collect_subject_work(
        namecode=namecode,
        conditions=conditions,
        tools=tools,
        args=args,
        raw_apps=raw_apps,
        raw_segments=raw_segments,
    )
    workers = _resolve_workers(args.workers, len(work))

    if not work:
        _log(f"[OpenSim Pipeline] DONE  {namecode}  (no runnable segments)")
        return []

    _log(f"  workers   : {workers}  "
         f"(shared across conditions; keep below core count if RAM-limited)")
    _log(f"  tasks     : {len(work)}  (condition × segment)")

    failures: list[dict] = []
    n_task = len(work)

    if workers == 1:
        for i_task, (condition, seg, apps) in enumerate(work, start=1):
            _log(
                f"\n===== ({i_task}/{n_task}) "
                f"condition={condition}  seg={seg}  START ====="
            )
            result = _run_one_segment(
                namecode, condition, seg, tools, apps, run_flags,
            )
            ok = _handle_segment_result(
                namecode=namecode,
                condition=condition,
                result=result,
                update_trouble_sheet=not args.no_trouble_sheet,
                dry_run=args.dry_run,
            )
            if ok:
                _log(
                    f"===== ({i_task}/{n_task}) "
                    f"condition={condition}  seg={seg}  COMPLETE ====="
                )
            else:
                failures.append(result)
                _log(
                    f"===== ({i_task}/{n_task}) "
                    f"condition={condition}  seg={seg}  FAILED ====="
                )
    else:
        _log(
            f"\n[OpenSim Pipeline] parallel subject pool  "
            f"workers={workers}  tasks={n_task}"
        )
        ctx = get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=ctx,
            max_tasks_per_child=1,
        ) as pool:
            futures = {
                pool.submit(
                    _run_one_segment,
                    namecode, condition, seg, tools, apps, run_flags,
                ): (condition, seg)
                for condition, seg, apps in work
            }
            done_n = 0
            for fut in as_completed(futures):
                condition, seg = futures[fut]
                done_n += 1
                try:
                    result = fut.result()
                except Exception as exc:
                    result = _fail_result(
                        seg, "worker", None, exc, condition=condition,
                    )
                ok = _handle_segment_result(
                    namecode=namecode,
                    condition=condition,
                    result=result,
                    update_trouble_sheet=not args.no_trouble_sheet,
                    dry_run=args.dry_run,
                )
                if ok:
                    _log(
                        f"===== ({done_n}/{n_task}) "
                        f"condition={condition}  seg={seg}  COMPLETE ====="
                    )
                else:
                    failures.append(result)
                    _log(
                        f"===== ({done_n}/{n_task}) "
                        f"condition={condition}  seg={seg}  FAILED ====="
                    )

    if (not args.dry_run) and (not args.no_trouble_sheet):
        try:
            _, removed = prune_resolved_troubles()
            if removed:
                _log(
                    f"[TROUBLE] pruned {len(removed)} resolved "
                    f"(result files present again)"
                )
            if failures or removed:
                sub_n = sub_number_for_namecode(namecode)
                out = refresh_progress_sheet([sub_n])
                _log(f"[TROUBLE] Detail sheet refreshed → {out}")
        except Exception as exc:
            _log(
                f"[TROUBLE] sheet refresh failed: "
                f"{type(exc).__name__}: {exc}"
            )

    _log(
        f"[OpenSim Pipeline] DONE  {namecode}  "
        f"conditions={len(conditions)}  tasks={n_task}  "
        f"failures={len(failures)}"
    )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenSim pipeline (ExtLoad / IK / ID / SO / BK / JR). "
                    "SO cases that only run from 0.05 s are a separate "
                    "retry: retry_so_edge.py"
    )
    parser.add_argument(
        "--namecode", default=None,
        help="Comma-separated SUB_Info namecode(s). "
             "Omit to run all subjects.",
    )
    parser.add_argument(
        "--condition", default=None,
        help="Comma-separated condition key(s) per selected subject. "
             "Omit to run all conditions of each subject.",
    )
    parser.add_argument(
        "--tools", default="extload,ik",
        help=f"Comma-separated subset of {list(VALID_TOOLS)} "
             "(execution order is fixed regardless of input order). "
             f"id runs only for {ID_APP}, once per segment.",
    )
    parser.add_argument(
        "--apps", default=None,
        help="Comma-separated app names; default is all protocol apps",
    )
    parser.add_argument(
        "--segments", default=None,
        help="Comma-separated segment labels (e.g., 1AB,1BC,1CA); "
             "default is all segments",
    )
    # Backward-compat alias in case old cells still use --sections.
    parser.add_argument("--sections", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true",
                        help="No file execution; only print planned actions")
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip a tool step when its pipeline output already exists "
             "(ExtLoad: SETUP_*.xml; IK: .mot; ID InverseDynamics / "
             "SO force / BK pos_global / JR ReactionLoads .sto). "
             "Missing outputs are still run.",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Parallel segment workers (default: 1 = sequential). "
             "Use 0 for os.cpu_count(). One shared pool per subject "
             "covers all of that subject's conditions so idle workers "
             "pick up the next condition's trials. Each worker exits "
             "after one segment to reclaim OpenSim memory. Keep modest "
             "if RAM-limited.",
    )
    parser.add_argument(
        "--no-trouble-sheet", action="store_true",
        help="Do not write pipeline_trouble.json / Detail ☒ on failures",
    )
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
    parser.add_argument(
        "--tool-timeout", type=float, default=DEFAULT_ANALYZE_TIMEOUT_S,
        help="Log-stall interval (seconds) for each SO/BK/JR AnalyzeTool "
             f"subprocess (default: {DEFAULT_ANALYZE_TIMEOUT_S:.0f} = 5 min). "
             "Every this many seconds the worker opensim.log is checked; "
             "if size/mtime are unchanged the job is killed as frozen and "
             "freeze_sim_time is recorded in pipeline_trouble.json / "
             "pipeline_freeze_sim_times.json. Use 0 to disable.",
    )
    parser.add_argument("--no-run-id", action="store_true",
                        help="Only write ID setup XMLs, do not execute the tool")
    parser.add_argument("--no-run-so", action="store_true",
                        help="Only write SO setup XMLs, do not execute the tool")
    parser.add_argument("--no-run-bk", action="store_true",
                        help="Only write BK setup XMLs, do not execute the tool")
    parser.add_argument("--no-run-jr", action="store_true",
                        help="Only write JR setup XMLs, do not execute the tool")
    args = parser.parse_args()

    if args.workers < 0:
        raise ValueError("--workers must be >= 0")
    if args.tool_timeout < 0:
        raise ValueError("--tool-timeout must be >= 0 (0 disables)")
    if args.tool_timeout == 0:
        args.tool_timeout = None

    namecodes = _pick_namecodes(args.namecode)
    tools = _parse_tools(args.tools)
    raw_segments = (
        args.segments if args.segments is not None else args.sections
    )

    # One job per subject: worker pool spans all selected conditions.
    jobs: list[tuple[str, list[str]]] = []
    for namecode in namecodes:
        jobs.append((namecode, _pick_conditions(namecode, args.condition)))

    _log("[OpenSim Pipeline] JOB PLAN")
    _log(f"  namecodes : {namecodes}")
    _log(f"  jobs      : {len(jobs)}  (one shared pool per subject)")
    _log(f"  tools     : {tools}")
    _log(f"  apps arg  : {args.apps!r}  (None → all protocol apps per condition)")
    _log(f"  segments  : {raw_segments!r}  (None → all segments per condition)")
    _log(f"  workers   : {args.workers}  (0 → cpu_count; clamped per subject)")
    _log(f"  dry_run   : {args.dry_run}")
    _log(f"  skip_existing : {args.skip_existing}")
    for i, (nc, conds) in enumerate(jobs, start=1):
        _log(f"    ({i}/{len(jobs)}) {nc} / conditions={conds}")

    all_failures: list[tuple[str, str, dict]] = []
    for i, (namecode, conditions) in enumerate(jobs, start=1):
        _log(
            f"\n######## SUBJECT ({i}/{len(jobs)}) {namecode}  "
            f"conditions={conditions} ########"
        )
        fails = _run_one_subject(
            namecode=namecode,
            conditions=conditions,
            tools=tools,
            args=args,
            raw_apps=args.apps,
            raw_segments=raw_segments,
        )
        for fr in fails:
            all_failures.append(
                (namecode, str(fr.get("condition", "?")), fr)
            )

    if all_failures:
        _log("\n[OpenSim Pipeline] FAILURE SUMMARY")
        for namecode, condition, fr in all_failures:
            _log(
                f"  {namecode} / {condition} / seg={fr.get('seg')}  "
                f"tool={fr.get('tool')}  app={fr.get('app')}  "
                f"{fr.get('error')}"
            )
        _log(
            f"[OpenSim Pipeline] COMPLETED WITH FAILURES  "
            f"n={len(all_failures)}"
        )
        sys.exit(1)

    _log("\n[OpenSim Pipeline] ALL REQUESTED WORK COMPLETE")


if __name__ == "__main__":
    main()

"""Per-tool handlers for the OpenSim pipeline.

Each handler is invoked once per ``(segment, app)`` (or per ``segment`` for
``bk``) by ``run_opensim_pipeline.py``.  All filesystem locations come from
``ConditionPaths`` / ``ResultPaths`` (see ``PATH_RULE.py``) and all model
selection goes through ``pipeline_rules`` so the kg-aware policy stays in a
single source of truth (see ``REFAC_RUN_TOOLS_PLAN.md`` §3.4 / §4.3).

ID uses ``InverseDynamicsTool`` (not ``AnalyzeTool``), so SET → RUN stays
in-process, matching IK and the Rehab reference ``step5_bk_grf_id``.

SET ↔ RUN isolation
-------------------
Reserve / residual / torque ``CoordinateActuator`` 의 모델 주입은 더 이상
이 모듈의 책임이 아니다.  ``Codes/b_Build_Model/add_reserve_actuators.py``
가 베이스 osim (``SUB{n}_Scaled.osim``) 단계에서 이미 baked-in 한다.
따라서 SO/JR SETUP XML 은 ``_Actuator`` 접미사 **없이** 베이스/변형 osim
경로를 그대로 가리킨다.

또한 SO/BK/JR 의 ``run_*`` 함수들은 **별도 Python 서브프로세스**
(``_run_analyze_subprocess.py``) 에서 ``AnalyzeTool.run()`` 만 수행한다.
이는 OLD 가 ``*_SET.py`` 와 ``*_RUN.py`` 를 두 파일로 분리해 실행하던
이유 (동일 프로세스 안에서 SET → RUN 직행 시 OpenSim 분석이 조용히
미수행되는 알려진 문제) 를 그대로 회피하기 위함이다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from lxml import etree

from pipeline_rules import (
    DEFAULT_ANALYZE_TIMEOUT_S,
    ik_suffix as _ik_suffix,
    ik_template as _ik_template,
    jr_suffixes as _jr_suffixes,
    require_id_app,
    resolve_model_path,
)


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SUBPROC_SCRIPT = os.path.join(_THIS_DIR, "_run_analyze_subprocess.py")

# OpenSim StaticOptimization progress lines in opensim.log (cwd of the process).
_OPENSIM_PERF_TIME_RE = re.compile(
    r"time\s*=\s*([0-9]+(?:\.[0-9]+)?)\s+Performance",
    re.IGNORECASE,
)


def _parse_last_opensim_sim_time(log_path: str) -> float | None:
    """Return the last StaticOptimization sim-time (s) from an opensim.log.

    Returns ``None`` when the file is missing or has no Performance lines.
    """
    if not log_path or not os.path.isfile(log_path):
        return None
    last: float | None = None
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = _OPENSIM_PERF_TIME_RE.search(line)
                if m:
                    last = float(m.group(1))
    except OSError:
        return None
    return last


def _opensim_log_fingerprint(log_path: str) -> tuple[int, int] | None:
    """Return ``(size, mtime_ns)`` for stall detection, or ``None`` if missing."""
    if not log_path:
        return None
    try:
        st = os.stat(log_path)
    except OSError:
        return None
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
    return (int(st.st_size), int(mtime_ns))


def _kill_process(proc: subprocess.Popen) -> None:
    """Best-effort terminate of an AnalyzeTool subprocess."""
    if proc.poll() is not None:
        return
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _maybe_add_opensim_dll_dir() -> None:
    """Add OpenSim DLL directory on Windows if available."""
    add_dll = getattr(os, "add_dll_directory", None)
    if add_dll is None:
        return
    dll_dir = "C:/OpenSim 4.5/bin"
    if os.path.isdir(dll_dir):
        add_dll(dll_dir)


# ──────────────────────────────────────────────────────────────────
# Subprocess-isolated RUN dispatcher
# ──────────────────────────────────────────────────────────────────
def _run_analyze_jobs(
    jobs: list[dict],
    *,
    timeout_s: float | None = DEFAULT_ANALYZE_TIMEOUT_S,
) -> None:
    """Execute one or more ``AnalyzeTool`` jobs in an isolated subprocess.

    Each job dict must carry: ``tool``, ``setup_xml``, ``model_path``.
    Optionally ``rename_after`` = ``list[[src, dst]]`` pairs applied
    after the corresponding ``.run()`` (used by JR to move the canonical
    ``..._ReactionLoads.sto`` to ``..._ReactionLoads_ground.sto`` before
    the subsequent child run overwrites it).

    ``timeout_s`` is the **log-stall interval** (default
    ``DEFAULT_ANALYZE_TIMEOUT_S`` = 300 s). Every that many seconds the
    worker's ``opensim.log`` fingerprint (size + mtime) is compared to the
    previous check; if unchanged the AnalyzeTool is treated as frozen,
    killed, and ``RuntimeError`` is raised so the pool worker can record
    trouble and continue — the worker itself is not killed (avoids
    BrokenProcessPool). Pass ``None`` to disable stall detection (no
    absolute wall-clock limit).

    Raises ``RuntimeError`` on non-zero exit or stall timeout; the JSON
    manifest is preserved on failure (deleted only on success).

    Each AnalyzeTool runs in a **unique cwd** so its ``opensim.log`` is not
    interleaved with sibling workers. On stall the last
    ``time = <sim> Performance`` value is attached as
    ``RuntimeError.freeze_sim_time`` for trouble / freeze-times JSON.
    """
    if not jobs:
        return
    if not os.path.isfile(_SUBPROC_SCRIPT):
        raise FileNotFoundError(
            f"Subprocess RUN script missing: {_SUBPROC_SCRIPT}"
        )

    workdir = tempfile.mkdtemp(prefix="opensim_run_")
    fd, manifest = tempfile.mkstemp(
        prefix="opensim_jobs_", suffix=".json", dir=workdir,
    )
    success = False
    opensim_log = os.path.join(workdir, "opensim.log")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)

        proc = subprocess.Popen(
            [sys.executable, _SUBPROC_SCRIPT, "--manifest", manifest],
            cwd=workdir,
        )
        returncode: int | None = None
        stalled = False
        try:
            if timeout_s is None:
                returncode = proc.wait()
            else:
                stall_s = float(timeout_s)
                last_fp = _opensim_log_fingerprint(opensim_log)
                while True:
                    try:
                        returncode = proc.wait(timeout=stall_s)
                        break
                    except subprocess.TimeoutExpired:
                        fp = _opensim_log_fingerprint(opensim_log)
                        if fp == last_fp:
                            stalled = True
                            _kill_process(proc)
                            returncode = proc.returncode
                            break
                        last_fp = fp
        except Exception:
            _kill_process(proc)
            raise

        if stalled:
            tools = ",".join(str(j.get("tool", "?")) for j in jobs)
            limit = f"{timeout_s:.0f}" if timeout_s is not None else "?"
            freeze_sim = _parse_last_opensim_sim_time(opensim_log)
            # Keep log + manifest for debugging (workdir not deleted).
            preserved_log = opensim_log if os.path.isfile(opensim_log) else None
            freeze_txt = (
                f"{freeze_sim:.6g}" if freeze_sim is not None else "unknown"
            )
            err = RuntimeError(
                f"AnalyzeTool subprocess killed after {limit}s log stall "
                f"(opensim.log unchanged; tool={tools}; "
                f"suspected frozen optimization).\n"
                f"  freeze_sim_time_s: {freeze_txt}\n"
                f"  Manifest preserved at: {manifest}"
                + (
                    f"\n  opensim.log preserved at: {preserved_log}"
                    if preserved_log
                    else ""
                )
            )
            err.freeze_sim_time = freeze_sim  # type: ignore[attr-defined]
            raise err

        if returncode != 0:
            freeze_sim = _parse_last_opensim_sim_time(opensim_log)
            freeze_txt = (
                f"{freeze_sim:.6g}" if freeze_sim is not None else "unknown"
            )
            err = RuntimeError(
                f"AnalyzeTool subprocess failed (exit {returncode}).\n"
                f"  freeze_sim_time_s: {freeze_txt}\n"
                f"  Manifest preserved at: {manifest}\n"
                f"  Re-run manually for debugging:\n"
                f"    {sys.executable} {_SUBPROC_SCRIPT} --manifest {manifest}"
            )
            err.freeze_sim_time = freeze_sim  # type: ignore[attr-defined]
            raise err
        success = True
    finally:
        if success:
            try:
                shutil.rmtree(workdir, ignore_errors=True)
            except OSError:
                pass



# ══════════════════════════════════════════════════════════════════
#  ExtLoad
# ══════════════════════════════════════════════════════════════════

def prepare_extload_setup(
    *,
    cp,
    seg: str,
    app: str,
    extload_template_path: str,
    dry_run: bool = False,
) -> str:
    """Create ExtLoad setup XML under the planned condition/section structure."""
    setup_xml_path = cp.setup_extload_path(seg, app)
    extload_mot_path = cp.extload_path(seg, app)

    if dry_run:
        return setup_xml_path

    tree = etree.parse(extload_template_path)
    root = tree.getroot()
    datafile_element = root.find(".//datafile")
    if datafile_element is None:
        raise ValueError(f"Template missing <datafile>: {extload_template_path}")

    datafile_element.text = extload_mot_path
    os.makedirs(os.path.dirname(setup_xml_path), exist_ok=True)
    tree.write(setup_xml_path, pretty_print=True, encoding="UTF-8", xml_declaration=True)
    return setup_xml_path


# ══════════════════════════════════════════════════════════════════
#  IK
# ══════════════════════════════════════════════════════════════════

def run_ik(
    *,
    cp,
    rp,
    seg: str,
    app: str,
    ik_template_default: str,
    ik_template_addbox: str,
    dry_run: bool = False,
) -> str:
    """Run IK and write setup/result files to planned structure.

    Note
    ----
    IK uses ``InverseKinematicsTool`` (not ``AnalyzeTool``) which is not
    affected by the SET↔RUN-in-same-process issue, so it stays in-process
    matching the OLD ``IK_RUN.py``.
    """
    trc_path = cp.trc_path(seg)
    model_path = resolve_model_path(rp, cp.cond, app, "ik",
                                    must_exist=not dry_run)
    suffix = _ik_suffix(app)
    setup_ik_path = cp.setup_ik_path(seg, suffix)
    ik_output_path = cp.ik_path(seg, suffix)
    ik_template_path = _ik_template(app,
                                    default=ik_template_default,
                                    addbox=ik_template_addbox)

    if dry_run:
        return setup_ik_path

    _maybe_add_opensim_dll_dir()
    import numpy as np
    import pandas as pd
    import opensim as osim

    df = pd.read_csv(trc_path, sep="\t", skiprows=4)
    trcdata = np.array(df)

    model = osim.Model(model_path)
    ik = osim.InverseKinematicsTool(ik_template_path)
    ik.setName(rp.sub_label)
    ik.set_marker_file(trc_path)
    ik.setModel(model)
    ik.setStartTime(trcdata[1, 1])
    ik.setEndTime(trcdata[-1, 1])
    ik.setOutputMotionFileName(ik_output_path)

    os.makedirs(os.path.dirname(setup_ik_path), exist_ok=True)
    ik.printToXML(setup_ik_path)
    ik.run()
    return setup_ik_path


# ──────────────────────────────────────────────────────────────────
# Shared AnalyzeTool helpers (SO / BK / JR)
# ──────────────────────────────────────────────────────────────────

def _read_trc_time_bounds(trc_path: str) -> tuple[float, float]:
    """Return (start_time, end_time) from a TRC file (skips 4 header rows)."""
    import numpy as np
    import pandas as pd

    df = pd.read_csv(trc_path, sep="\t", skiprows=4)
    trcdata = np.array(df)
    return float(trcdata[1, 1]), float(trcdata[-1, 1])


def _resolve_analyze_window(
    trc_path: str,
    start_time: float | None = None,
) -> tuple[float, float]:
    """TRC window, optionally overriding the start.

    End time stays the TRC end. ``start_time`` is the edge-retry hook
    (see ``retry_so_edge.py``); the main pipeline passes ``None``.
    """
    t0, t1 = _read_trc_time_bounds(trc_path)
    if start_time is None:
        return t0, t1
    t0 = float(start_time)
    if not t0 < t1:
        raise ValueError(
            f"start_time {t0} must be < end time {t1} (trc={trc_path})"
        )
    return t0, t1


def _read_motion_time_bounds(motion_path: str) -> tuple[float, float]:
    """Return (start_time, end_time) from an OpenSim ``.mot`` / ``.sto``.

    Reads the first column of the data table after ``endheader``. Used by ID
    so the tool window matches the IK coordinates file it actually consumes
    (same source as Rehab ``step5_bk_grf_id``).
    """
    with open(motion_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    start = 0
    for i, line in enumerate(lines):
        if line.strip().lower() == "endheader":
            start = i + 1
            break

    data_rows: list[str] = []
    header_skipped = False
    for line in lines[start:]:
        s = line.strip()
        if not s:
            continue
        if not header_skipped:
            header_skipped = True
            continue
        data_rows.append(s)
    if not data_rows:
        raise ValueError(f"No data rows in motion file: {motion_path}")

    t0 = float(data_rows[0].split()[0])
    t1 = float(data_rows[-1].split()[0])
    if t1 < t0:
        raise ValueError(
            f"Motion time bounds inverted ({t0} > {t1}): {motion_path}"
        )
    return t0, t1


def _new_analyze_tool(*, osim_mod, name: str, model_path: str, model,
                      coordinates_path: str, extload_xml: str,
                      results_dir: str, t0: float, t1: float,
                      lowpass_cutoff: float = 6.0,
                      controls_path: str | None = None):
    """Construct a populated ``AnalyzeTool`` with the common settings."""
    analyze = osim_mod.AnalyzeTool()
    analyze.setName(name)
    analyze.setModel(model)
    analyze.setModelFilename(model_path)
    analyze.setReplaceForceSet(False)
    if controls_path is not None:
        analyze.setControlsFileName(controls_path)
    analyze.setCoordinatesFileName(coordinates_path)
    analyze.setLowpassCutoffFrequency(lowpass_cutoff)
    analyze.setSolveForEquilibrium(True)
    analyze.setStartTime(t0)
    analyze.setFinalTime(t1)
    analyze.setExternalLoadsFileName(extload_xml)
    analyze.setResultsDir(results_dir)
    return analyze


def _ik_inputs_for_app(cp, seg: str, app: str) -> tuple[str, str]:
    """Return (ik_mot_path, setup_extload_xml) for an SO/JR input app.

    ``AddBox`` consumes the ``IK_AddBox`` motion (kg-aware AddBox model);
    other apps consume the base ``IK`` motion.  ExtLoad XML is always the
    one generated for that app.
    """
    ik_suffix = _ik_suffix(app)
    ik_mot = cp.ik_path(seg, ik_suffix)
    extload_xml = cp.setup_extload_path(seg, app)
    return ik_mot, extload_xml


# ══════════════════════════════════════════════════════════════════
#  ID  (Inverse Dynamics — HeavyHand only)
# ══════════════════════════════════════════════════════════════════
#
# Adapted from Rehab ``step5_bk_grf_id``:
#   InverseDynamicsTool + IK coordinates + ExtLoad XML + exclude Muscles
#   + 6 Hz low-pass + generalized-force .sto.
#
# Restricted to ``pipeline_rules.ID_APP`` (HeavyHand). The runner must not
# call this once per protocol app. InverseDynamicsTool is not subject to
# the AnalyzeTool SET↔RUN silent-skip bug, so RUN stays in-process (like IK).
# ══════════════════════════════════════════════════════════════════

def prepare_id_setup(
    *,
    cp,
    rp,
    seg: str,
    app: str,
    lowpass_cutoff: float = 6.0,
    dry_run: bool = False,
) -> str:
    """Write ``SETUP_ID_*.xml`` for HeavyHand only.

    Inputs
    ------
    - coordinates: HeavyHand IK motion (base IK, not AddBox)
    - external loads: HeavyHand ExtLoad SETUP XML
    - model: kg-aware HeavyHand osim (same variant as SO/JR)
    """
    app = require_id_app(app)
    setup_id_xml = cp.setup_id_path(seg, app)
    results_dir = cp.id_dir(cp.seg_to_section(seg), app)
    output_sto = cp.id_path(seg, app)
    model_path = resolve_model_path(rp, cp.cond, app, "id",
                                    must_exist=not dry_run)

    if dry_run:
        return setup_id_xml

    ik_mot, extload_xml = _ik_inputs_for_app(cp, seg, app)
    missing = [p for p in (ik_mot, extload_xml) if not os.path.isfile(p)]
    if missing:
        raise FileNotFoundError(
            "ID inputs missing:\n  " + "\n  ".join(missing) + "\n"
            "  Run --tools extload,ik first."
        )

    _maybe_add_opensim_dll_dir()
    import opensim as osim

    t0, t1 = _read_motion_time_bounds(ik_mot)
    model = osim.Model(model_path)
    id_tool = osim.InverseDynamicsTool()
    id_tool.setName(f"{rp.sub_label}_{cp.cond}_{seg}_{app}")
    id_tool.setModel(model)
    # InverseDynamicsTool uses setModelFileName (capital N). AnalyzeTool's
    # setModelFilename does not exist on this class (OpenSim 4.5).
    id_tool.setModelFileName(model_path)
    id_tool.setCoordinatesFileName(ik_mot)
    id_tool.setLowpassCutoffFrequency(lowpass_cutoff)
    id_tool.setStartTime(t0)
    id_tool.setEndTime(t1)
    id_tool.setExternalLoadsFileName(extload_xml)
    # Exclude muscle forces so the .sto is net generalized force (Rehab ID).
    id_tool.setExcludedForces(osim.ArrayStr("Muscles", 1))
    id_tool.setResultsDir(results_dir)
    id_tool.setOutputGenForceFileName(os.path.basename(output_sto))

    os.makedirs(os.path.dirname(setup_id_xml), exist_ok=True)
    id_tool.printToXML(setup_id_xml)
    return setup_id_xml


def run_id(
    *,
    cp,
    rp,
    seg: str,
    app: str,
    dry_run: bool = False,
) -> str:
    """Run a previously prepared ``SETUP_ID_*.xml`` for one (segment, app).

    Reloads the XML into a fresh ``InverseDynamicsTool`` and binds the model
    again, so ``--no-run-id`` setup files can be executed later. Stays
    in-process: this is not ``AnalyzeTool``. HeavyHand only.
    """
    app = require_id_app(app)
    setup_id_xml = cp.setup_id_path(seg, app)
    output_sto = cp.id_path(seg, app)
    if dry_run:
        return setup_id_xml
    if not os.path.isfile(setup_id_xml):
        raise FileNotFoundError(
            f"ID setup missing: {setup_id_xml}\n"
            "  Run with --tools id (setup is created on first invocation)."
        )

    model_path = resolve_model_path(rp, cp.cond, app, "id", must_exist=True)
    _maybe_add_opensim_dll_dir()
    import opensim as osim

    model = osim.Model(model_path)
    id_tool = osim.InverseDynamicsTool(setup_id_xml)
    id_tool.setModel(model)
    # InverseDynamicsTool uses setModelFileName (capital N). AnalyzeTool's
    # setModelFilename does not exist on this class (OpenSim 4.5).
    id_tool.setModelFileName(model_path)
    ok = id_tool.run()
    if ok is False:
        raise RuntimeError(f"InverseDynamicsTool.run() returned False: {setup_id_xml}")
    if not os.path.isfile(output_sto):
        raise FileNotFoundError(
            f"ID finished but output missing: {output_sto}\n"
            f"  setup={setup_id_xml}"
        )
    return output_sto


# ══════════════════════════════════════════════════════════════════
#  SO  (Static Optimization)
# ══════════════════════════════════════════════════════════════════

def prepare_so_setup(
    *,
    cp,
    rp,
    seg: str,
    app: str,
    lowpass_cutoff: float = 6.0,
    step_interval: int = 1,
    activation_exponent: int = 2,
    convergence_criterion: float = 1e-4,
    max_iterations: int = 100,
    dry_run: bool = False,
    start_time: float | None = None,
) -> str:
    """Write ``SETUP_SO_*.xml`` for one (segment, app).

    The setup XML's ``<model_file>`` points at the kg-aware **base** osim
    (``SUB{n}_Scaled[_HeavyHand_{w}kg|_SplitBox_{w}kg].osim``) — reserves
    are assumed to be baked in by ``b_Build_Model/add_reserve_actuators``.
    No ``_Actuator`` suffix is generated here.

    ``start_time`` overrides the TRC start (default). Used by
    ``retry_so_edge.py`` for the 0.05 s edge retry; the main pipeline
    leaves it unset.
    """
    setup_so_xml = cp.setup_so_path(seg, app)
    results_dir = cp.so_dir(cp.seg_to_section(seg), app)
    model_path = resolve_model_path(rp, cp.cond, app, "so",
                                    must_exist=not dry_run)

    if dry_run:
        return setup_so_xml

    _maybe_add_opensim_dll_dir()
    import opensim as osim

    trc_path = cp.trc_path(seg)
    t0, t1 = _resolve_analyze_window(trc_path, start_time)
    ik_mot, extload_xml = _ik_inputs_for_app(cp, seg, app)

    model = osim.Model(model_path)
    analyze = _new_analyze_tool(
        osim_mod=osim,
        name=f"{rp.sub_label}_{cp.cond}_{seg}_{app}",
        model_path=model_path,
        model=model,
        coordinates_path=ik_mot,
        extload_xml=extload_xml,
        results_dir=results_dir,
        t0=t0, t1=t1,
        lowpass_cutoff=lowpass_cutoff,
    )

    so = osim.StaticOptimization()
    so.setModel(model)
    so.setStartTime(t0)
    so.setEndTime(t1)
    so.setStepInterval(step_interval)
    so.setInDegrees(True)
    so.setUseModelForceSet(True)
    so.setActivationExponent(activation_exponent)
    so.setUseMusclePhysiology(True)
    so.setConvergenceCriterion(convergence_criterion)
    so.setMaxIterations(max_iterations)
    analyze.getAnalysisSet().adoptAndAppend(so)

    os.makedirs(os.path.dirname(setup_so_xml), exist_ok=True)
    analyze.printToXML(setup_so_xml)
    return setup_so_xml


def run_so(
    *,
    cp,
    rp,
    seg: str,
    app: str,
    dry_run: bool = False,
    timeout_s: float | None = DEFAULT_ANALYZE_TIMEOUT_S,
) -> str:
    """Run a previously prepared ``SETUP_SO_*.xml`` for one (segment, app).

    Executes inside an isolated Python subprocess so that the in-process
    OpenSim state left over by ``prepare_so_setup`` (or by any earlier
    SETUP build) cannot suppress this run.  See module docstring.
    """
    setup_so_xml = cp.setup_so_path(seg, app)
    if dry_run:
        return setup_so_xml
    if not os.path.isfile(setup_so_xml):
        raise FileNotFoundError(
            f"SO setup missing: {setup_so_xml}\n"
            "  Run with --tools so (setup is created on first invocation)."
        )

    model_path = resolve_model_path(rp, cp.cond, app, "so", must_exist=True)
    _run_analyze_jobs([{
        "tool": "so",
        "setup_xml": setup_so_xml,
        "model_path": model_path,
    }], timeout_s=timeout_s)
    return setup_so_xml


# ══════════════════════════════════════════════════════════════════
#  BK  (BodyKinematics — segment-level, app-agnostic)
# ══════════════════════════════════════════════════════════════════

def prepare_bk_setup(
    *,
    cp,
    rp,
    seg: str,
    bk_ik_app: str = "MeasuredEHF",
    lowpass_cutoff: float = 6.0,
    step_interval: int = 1,
    dry_run: bool = False,
    start_time: float | None = None,
) -> str:
    """Write ``SETUP_BK_*.xml`` for one segment (no app dimension).

    BodyKinematics is purely kinematic, so it uses the **base** osim
    (``SUB{n}_Scaled.osim``) and the ``IK`` (non-AddBox) motion by default.
    ``bk_ik_app`` lets callers override which IK / ExtLoad to bind to.

    ``start_time`` overrides the TRC start (default). Used by
    ``retry_so_edge.py`` so BK matches the truncated SO/JR window.
    """
    setup_bk_xml = cp.setup_bk_path(seg)
    results_dir = cp.bk_dir(cp.seg_to_section(seg))

    base_model_path = rp.model_path("")

    if dry_run:
        return setup_bk_xml

    if not os.path.isfile(base_model_path):
        raise FileNotFoundError(
            f"Base osim missing for BK: {base_model_path}\n"
            "  Run Codes/b_Build_Model/_b_Main.ipynb first."
        )

    _maybe_add_opensim_dll_dir()
    import opensim as osim

    trc_path = cp.trc_path(seg)
    t0, t1 = _resolve_analyze_window(trc_path, start_time)
    ik_mot, extload_xml = _ik_inputs_for_app(cp, seg, bk_ik_app)

    model = osim.Model(base_model_path)
    analyze = _new_analyze_tool(
        osim_mod=osim,
        name=f"{rp.sub_label}_{cp.cond}_{seg}",
        model_path=base_model_path,
        model=model,
        coordinates_path=ik_mot,
        extload_xml=extload_xml,
        results_dir=results_dir,
        t0=t0, t1=t1,
        lowpass_cutoff=lowpass_cutoff,
    )

    bk = osim.BodyKinematics()
    bk.setName("BodyKinematics")
    bk.setStartTime(t0)
    bk.setEndTime(t1)
    bk.setStepInterval(step_interval)
    bk.setInDegrees(True)
    analyze.getAnalysisSet().adoptAndAppend(bk)

    os.makedirs(os.path.dirname(setup_bk_xml), exist_ok=True)
    analyze.printToXML(setup_bk_xml)
    return setup_bk_xml


def run_bk(
    *,
    cp,
    rp,
    seg: str,
    dry_run: bool = False,
    timeout_s: float | None = DEFAULT_ANALYZE_TIMEOUT_S,
) -> str:
    """Run a previously prepared ``SETUP_BK_*.xml`` for one segment."""
    setup_bk_xml = cp.setup_bk_path(seg)
    if dry_run:
        return setup_bk_xml
    if not os.path.isfile(setup_bk_xml):
        raise FileNotFoundError(
            f"BK setup missing: {setup_bk_xml}\n"
            "  Run with --tools bk (setup is created on first invocation)."
        )

    base_model_path = rp.model_path("")
    _run_analyze_jobs([{
        "tool": "bk",
        "setup_xml": setup_bk_xml,
        "model_path": base_model_path,
    }], timeout_s=timeout_s)
    return setup_bk_xml


# ══════════════════════════════════════════════════════════════════
#  JR  (JointReaction)
# ══════════════════════════════════════════════════════════════════
#
# Per ``STRUCTURE_PLAN.md`` the ``JR_<App>/`` folder may hold one or two
# setup/result pairs depending on app:
#   - non-AddBox  → ``SETUP_JR_..._<app>.xml``         (express_in_frame=child)
#                   → ``..._JointReaction_ReactionLoads.sto``
#   - AddBox      → ALSO ``SETUP_JR_..._<app>_ground.xml`` (default ground)
#                   → ``..._JointReaction_ReactionLoads_ground.sto``
#
# OpenSim's AnalyzeTool writes a fixed basename (``..._ReactionLoads.sto``).
# To keep two files in the same folder we run ``ground`` FIRST and rename
# the output (in the same subprocess between consecutive ``.run()`` calls),
# then run ``child`` which produces the canonical
# ``..._ReactionLoads.sto``.  ``pipeline_rules.jr_suffixes(app)`` decides
# which set of suffixes applies.
# ══════════════════════════════════════════════════════════════════

def _set_express_in_frame_child(setup_xml_path: str) -> None:
    """Edit ``<express_in_frame>`` element in a JR setup XML → 'child'."""
    tree = etree.parse(setup_xml_path)
    root = tree.getroot()
    el = root.find(".//express_in_frame")
    if el is None:
        # OpenSim sometimes uses a different tag depending on version; bail
        # out loudly so the user can inspect the template.
        raise ValueError(
            f"<express_in_frame> not found in {setup_xml_path}; cannot "
            "switch JR frame to 'child'."
        )
    el.text = "child"
    tree.write(setup_xml_path, pretty_print=True,
               encoding="UTF-8", xml_declaration=True)


def _jr_suffix_order(app: str) -> list[str]:
    """Stable order: ``ground`` first (so its output gets renamed before the
    canonical child run overwrites it), then ``""`` (child)."""
    return sorted(_jr_suffixes(app), key=lambda s: 0 if s == "ground" else 1)


def prepare_jr_setup(
    *,
    cp,
    rp,
    seg: str,
    app: str,
    lowpass_cutoff: float = 6.0,
    step_interval: int = 1,
    dry_run: bool = False,
    start_time: float | None = None,
) -> list[str]:
    """Write one or two ``SETUP_JR_*.xml`` files for one (segment, app).

    Returns the list of setup XML paths actually written / planned, in the
    fixed ``ground → child`` order.

    ``start_time`` overrides the TRC start (default). Used by
    ``retry_so_edge.py`` so JR matches the truncated SO window.
    """
    suffixes = _jr_suffix_order(app)
    setup_paths = [cp.setup_jr_path(seg, app, suffix) for suffix in suffixes]

    if dry_run:
        return setup_paths

    model_path = resolve_model_path(rp, cp.cond, app, "jr", must_exist=True)

    _maybe_add_opensim_dll_dir()
    import opensim as osim

    trc_path = cp.trc_path(seg)
    t0, t1 = _resolve_analyze_window(trc_path, start_time)
    ik_mot, extload_xml = _ik_inputs_for_app(cp, seg, app)

    # SO outputs are mandatory inputs for JR (controls + forces).
    so_controls = cp.so_path(seg, app, "activation")
    so_forces   = cp.so_path(seg, app, "force")

    results_dir = cp.jr_dir(cp.seg_to_section(seg), app)
    os.makedirs(results_dir, exist_ok=True)

    for suffix, setup_xml in zip(suffixes, setup_paths):
        model = osim.Model(model_path)
        analyze = _new_analyze_tool(
            osim_mod=osim,
            name=f"{rp.sub_label}_{cp.cond}_{seg}_{app}",
            model_path=model_path,
            model=model,
            coordinates_path=ik_mot,
            extload_xml=extload_xml,
            results_dir=results_dir,
            t0=t0, t1=t1,
            lowpass_cutoff=lowpass_cutoff,
            controls_path=so_controls,
        )

        jr = osim.JointReaction()
        jr.setName("JointReaction")
        jr.setStartTime(t0)
        jr.setEndTime(t1)
        jr.setStepInterval(step_interval)
        jr.setInDegrees(True)
        jr.setForcesFileName(so_forces)
        analyze.getAnalysisSet().adoptAndAppend(jr)

        os.makedirs(os.path.dirname(setup_xml), exist_ok=True)
        analyze.printToXML(setup_xml)

        # Default OpenSim JR frame is 'ground'; flip to 'child' for the
        # canonical (suffix-less) setup.
        if suffix == "":
            _set_express_in_frame_child(setup_xml)

    return setup_paths


def run_jr(
    *,
    cp,
    rp,
    seg: str,
    app: str,
    dry_run: bool = False,
    timeout_s: float | None = DEFAULT_ANALYZE_TIMEOUT_S,
) -> list[str]:
    """Run all JR setup XMLs for one (segment, app), renaming ground output.

    All jobs are executed in a SINGLE isolated subprocess so that the
    rename step (canonical → ``_ground``) sits between the two consecutive
    ``.run()`` calls without going back to the SET-polluted main process.
    """
    suffixes = _jr_suffix_order(app)
    setup_paths = [cp.setup_jr_path(seg, app, suffix) for suffix in suffixes]

    if dry_run:
        return setup_paths

    model_path = resolve_model_path(rp, cp.cond, app, "jr", must_exist=True)
    canonical_jr_sto = cp.jr_path(seg, app, "")

    jobs: list[dict] = []
    for suffix, setup_xml in zip(suffixes, setup_paths):
        if not os.path.isfile(setup_xml):
            raise FileNotFoundError(
                f"JR setup missing: {setup_xml}\n"
                "  Run with --tools jr (setups are created on first invocation)."
            )
        job: dict = {
            "tool": "jr",
            "setup_xml": setup_xml,
            "model_path": model_path,
        }
        if suffix:
            # Rename the canonical sto (just produced by this job) to its
            # suffixed name BEFORE the next (child) job overwrites it.
            suffixed = cp.jr_path(seg, app, suffix)
            job["rename_after"] = [[canonical_jr_sto, suffixed]]
        jobs.append(job)

    _run_analyze_jobs(jobs, timeout_s=timeout_s)
    return setup_paths

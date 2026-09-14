"""Free-box OpenSim IK + BodyKinematics + StatesReporter (Approach-5 Load path).

Reimplements vendor ``LoadIKAPP5`` / ``LoadBKAPP5`` / ``LoadStatesAPP5`` against
``BOX_with_markers.osim`` without importing ``_vendor`` / General at runtime.

AnalyzeTool SET→RUN is isolated via ``_run_analyze_subprocess.py`` (same
pattern as the human pipeline) to avoid silent OpenSim skip.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Optional, Sequence

_THIS = os.path.dirname(os.path.abspath(__file__))
_RUN_TOOLS = os.path.dirname(_THIS)
_CODES = os.path.dirname(_RUN_TOOLS)
for _p in (_CODES, _RUN_TOOLS, _THIS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_SUBPROC_SCRIPT = os.path.join(_RUN_TOOLS, "_run_analyze_subprocess.py")

try:
    from . import boxwrench_config as cfg
    from . import boxwrench_paths as bpaths
except ImportError:
    import boxwrench_config as cfg
    import boxwrench_paths as bpaths


def _maybe_add_opensim_dll_dir() -> None:
    add_dll = getattr(os, "add_dll_directory", None)
    if add_dll is None:
        return
    dll_dir = "C:/OpenSim 4.5/bin"
    if os.path.isdir(dll_dir):
        add_dll(dll_dir)


def require_opensim():
    """Import opensim or raise a clear error."""
    _maybe_add_opensim_dll_dir()
    try:
        import opensim as osim  # noqa: WPS433
    except Exception as exc:  # pragma: no cover - env dependent
        raise RuntimeError(
            "OpenSim Python package unavailable. Use the ``osim`` conda env "
            r"(e.g. C:\Users\ok\anaconda3\envs\osim\python.exe)."
        ) from exc
    return osim


def _run_analyze_subprocess(jobs: list[dict]) -> None:
    if not jobs:
        return
    if not os.path.isfile(_SUBPROC_SCRIPT):
        raise FileNotFoundError(f"Missing Analyze RUN helper: {_SUBPROC_SCRIPT}")
    fd, manifest = tempfile.mkstemp(prefix="boxwrench_analyze_", suffix=".json")
    os.close(fd)
    try:
        with open(manifest, "w", encoding="utf-8") as f:
            json.dump(jobs, f)
        cmd = [sys.executable, _SUBPROC_SCRIPT, "--manifest", manifest]
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"AnalyzeTool subprocess failed (exit={proc.returncode}). "
                f"manifest kept: {manifest}"
            )
    finally:
        if os.path.isfile(manifest):
            try:
                os.remove(manifest)
            except OSError:
                pass


def run_box_ik(
    *,
    model_path: str,
    trc_path: str,
    out_mot: str,
    setup_xml: str,
    marker_names: Sequence[str] = cfg.BOX_IK_MARKER_NAMES,
    marker_weight: float = cfg.LOAD_IK_MARKER_WEIGHT,
    dry_run: bool = False,
) -> str:
    """IK of free-joint box markers → ``out_mot`` (vendor LoadIK pattern)."""
    os.makedirs(os.path.dirname(out_mot) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(setup_xml) or ".", exist_ok=True)
    if dry_run:
        return setup_xml
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Box model missing: {model_path}")
    if not os.path.isfile(trc_path):
        raise FileNotFoundError(f"TRC missing: {trc_path}")

    osim = require_opensim()
    model = osim.Model(model_path)
    model.initSystem()

    marker_data = osim.MarkerData(trc_path)
    t0 = float(marker_data.getStartFrameTime())
    t1 = float(marker_data.getLastFrameTime())

    ik = osim.InverseKinematicsTool()
    ik.setModel(model)
    ik.set_marker_file(trc_path)
    ik.setStartTime(t0)
    ik.setEndTime(t1)
    ik.setOutputMotionFileName(out_mot)
    ik.set_report_errors(True)

    task_set = ik.getIKTaskSet()
    # Clear any default tasks then append box corners only.
    while task_set.getSize() > 0:
        task_set.remove(0)
    for name in marker_names:
        task = osim.IKMarkerTask()
        task.setName(str(name))
        task.setApply(True)
        task.setWeight(float(marker_weight))
        task_set.cloneAndAppend(task)

    ik.printToXML(setup_xml)
    ok = ik.run()
    if ok is False:
        raise RuntimeError(f"Box IK failed: {setup_xml}")
    if not os.path.isfile(out_mot):
        raise FileNotFoundError(f"Box IK did not write MOT: {out_mot}")
    return setup_xml


def prepare_box_bk_setup(
    *,
    model_path: str,
    ik_mot: str,
    results_dir: str,
    setup_xml: str,
    analyze_name: str,
    lowpass_cutoff: float = cfg.LOAD_ANALYZE_CUTOFF_HZ,
    dry_run: bool = False,
) -> str:
    """Write SETUP XML for BodyKinematics on the free box (no ExtLoad)."""
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(os.path.dirname(setup_xml) or ".", exist_ok=True)
    if dry_run:
        return setup_xml
    if not os.path.isfile(ik_mot):
        raise FileNotFoundError(f"Box IK MOT missing for BK: {ik_mot}")

    osim = require_opensim()
    storage = osim.Storage(ik_mot)
    t0 = float(storage.getFirstTime())
    t1 = float(storage.getLastTime())

    model = osim.Model(model_path)
    at = osim.AnalyzeTool()
    at.setName(analyze_name)
    at.setModel(model)
    at.setModelFilename(model_path)
    at.setResultsDir(results_dir)
    at.setInitialTime(t0)
    at.setFinalTime(t1)
    at.setSolveForEquilibrium(False)
    at.setCoordinatesFileName(ik_mot)
    at.setLowpassCutoffFrequency(float(lowpass_cutoff))

    bk = osim.BodyKinematics()
    bk.setOn(True)
    bk.setName("BodyKinematics")
    bk.setStartTime(t0)
    bk.setEndTime(t1)
    bk.setInDegrees(True)
    at.getAnalysisSet().cloneAndAppend(bk)

    at.printToXML(setup_xml)
    return setup_xml


def prepare_box_states_setup(
    *,
    model_path: str,
    ik_mot: str,
    results_dir: str,
    setup_xml: str,
    analyze_name: str,
    lowpass_cutoff: float = cfg.LOAD_ANALYZE_CUTOFF_HZ,
    dry_run: bool = False,
) -> str:
    """Write SETUP XML for StatesReporter on the free box."""
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(os.path.dirname(setup_xml) or ".", exist_ok=True)
    if dry_run:
        return setup_xml
    if not os.path.isfile(ik_mot):
        raise FileNotFoundError(f"Box IK MOT missing for States: {ik_mot}")

    osim = require_opensim()
    storage = osim.Storage(ik_mot)
    t0 = float(storage.getFirstTime())
    t1 = float(storage.getLastTime())

    model = osim.Model(model_path)
    at = osim.AnalyzeTool()
    at.setName(analyze_name)
    at.setModel(model)
    at.setModelFilename(model_path)
    at.setResultsDir(results_dir)
    at.setInitialTime(t0)
    at.setFinalTime(t1)
    at.setSolveForEquilibrium(False)
    at.setCoordinatesFileName(ik_mot)
    at.setLowpassCutoffFrequency(float(lowpass_cutoff))

    sr = osim.StatesReporter()
    sr.setOn(True)
    sr.setName("StatesReporter")
    sr.setStartTime(t0)
    sr.setEndTime(t1)
    at.getAnalysisSet().cloneAndAppend(sr)

    at.printToXML(setup_xml)
    return setup_xml


def run_box_analyze_jobs(
    *,
    model_path: str,
    setups: Sequence[tuple[str, str]],
    dry_run: bool = False,
) -> None:
    """Run prepared AnalyzeTool setups in an isolated subprocess.

    ``setups``: sequence of ``(tool_tag, setup_xml)`` e.g. ``(\"bk\", path)``.
    """
    if dry_run:
        return
    jobs = [
        {"tool": tool, "setup_xml": xml, "model_path": model_path}
        for tool, xml in setups
    ]
    _run_analyze_subprocess(jobs)


def ensure_load_kinematics(
    *,
    namecode: str,
    condition: str,
    seg: str,
    model_path: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, str]:
    """Run free-box IK → BK + States if outputs missing (or ``force``).

    Returns paths: ``trc``, ``ik_mot``, ``bk_vel``, ``bk_pos``, ``states``.
    """
    model_path = model_path or cfg.DEFAULT_BOX_WITH_MARKERS_OSIM
    trc = bpaths.trc_path(namecode, condition, seg)
    ikp = bpaths.load_ik_paths(namecode, condition, seg)
    bkp = bpaths.load_bk_paths(namecode, condition, seg)
    stp = bpaths.load_states_paths(namecode, condition, seg)

    need_ik = force or not os.path.isfile(ikp["mot"])
    need_bk = force or not (
        os.path.isfile(bkp["vel"]) and os.path.isfile(bkp["pos"])
    )
    need_st = force or not os.path.isfile(stp["states"])

    if need_ik:
        run_box_ik(
            model_path=model_path,
            trc_path=trc,
            out_mot=ikp["mot"],
            setup_xml=ikp["setup"],
            dry_run=dry_run,
        )

    analyze_jobs: list[tuple[str, str]] = []
    if need_bk:
        prepare_box_bk_setup(
            model_path=model_path,
            ik_mot=ikp["mot"],
            results_dir=bkp["dir"],
            setup_xml=bkp["setup"],
            analyze_name=bkp["prefix"],
            dry_run=dry_run,
        )
        analyze_jobs.append(("bk", bkp["setup"]))
    if need_st:
        prepare_box_states_setup(
            model_path=model_path,
            ik_mot=ikp["mot"],
            results_dir=stp["dir"],
            setup_xml=stp["setup"],
            analyze_name=stp["prefix"],
            dry_run=dry_run,
        )
        analyze_jobs.append(("states", stp["setup"]))

    if analyze_jobs:
        run_box_analyze_jobs(
            model_path=model_path, setups=analyze_jobs, dry_run=dry_run
        )

    if not dry_run:
        for label, path in (
            ("bk_vel", bkp["vel"]),
            ("bk_pos", bkp["pos"]),
            ("states", stp["states"]),
        ):
            if not os.path.isfile(path):
                raise FileNotFoundError(
                    f"Expected {label} after free-box Analyze: {path}"
                )

    return {
        "trc": trc,
        "model": model_path,
        "ik_mot": ikp["mot"],
        "ik_setup": ikp["setup"],
        "bk_vel": bkp["vel"],
        "bk_pos": bkp["pos"],
        "bk_setup": bkp["setup"],
        "states": stp["states"],
        "states_setup": stp["setup"],
    }

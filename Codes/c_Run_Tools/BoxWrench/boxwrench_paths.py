"""Resolve BoxWrench / free-box Load paths (local OpenSim_Process vs Dropbox).

``PATH_RULE.ResultPaths`` creates trees under the **repo** ``OpenSim_Process/_Main_``.
Processed subject data often lives under ``COWORK_OPENSIM_DIR`` (Dropbox). This
module prefers an existing file/tree and falls back across both roots.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Optional

_THIS = os.path.dirname(os.path.abspath(__file__))
_RUN_TOOLS = os.path.dirname(_THIS)
_CODES = os.path.dirname(_RUN_TOOLS)
for _p in (_CODES, _RUN_TOOLS, _THIS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import PATH_RULE as _path  # noqa: E402

try:
    from . import boxwrench_config as cfg
except ImportError:
    import boxwrench_config as cfg


def _first_existing_file(candidates: Iterable[str]) -> Optional[str]:
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def _first_existing_dir(candidates: Iterable[str]) -> Optional[str]:
    for p in candidates:
        if p and os.path.isdir(p):
            return p
    return None


def opensim_roots() -> list[str]:
    """Ordered OpenSim_Process/_Main_ candidates (local then cowork)."""
    roots: list[str] = []
    for r in (_path.OPENSIM_DIR, _path.COWORK_OPENSIM_DIR):
        if r and r not in roots:
            roots.append(r)
    return roots


def subject_root(namecode: str, *, prefer_existing: bool = True) -> str:
    """``…/_Main_/<protocol>/SUB{n}`` — prefer root that already has Markers data."""
    rp = _path.ResultPaths(namecode)
    candidates = [
        os.path.join(root, rp.protocol, rp.sub_label) for root in opensim_roots()
    ]
    if prefer_existing:
        # Prefer a tree that already has segment Markers (not an empty local mkdir).
        for base in candidates:
            markers_hit = False
            if os.path.isdir(base):
                for dirpath, _dirnames, filenames in os.walk(base):
                    if os.path.basename(dirpath) == "Markers" and any(
                        f.lower().endswith(".trc") for f in filenames
                    ):
                        markers_hit = True
                        break
            if markers_hit:
                return base
        hit = _first_existing_dir(candidates)
        if hit is not None:
            return hit
    os.makedirs(candidates[0], exist_ok=True)
    return candidates[0]


def subject_root_for_segment(namecode: str, condition: str, seg: str) -> str:
    """Subject root that owns the segment TRC (Dropbox or local)."""
    try:
        trc = trc_path(namecode, condition, seg)
    except FileNotFoundError:
        return subject_root(namecode)
    # …/SUB{n}/{cond}/{section}/Markers/*.trc → SUB{n}
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(trc))))


def section_folder(namecode: str, condition: str, seg: str, folder: str) -> str:
    rp = _path.ResultPaths(namecode)
    section = rp.seg_to_section(seg)
    base = subject_root_for_segment(namecode, condition, seg)
    d = os.path.join(base, condition, section, folder)
    os.makedirs(d, exist_ok=True)
    return d


def trc_path(namecode: str, condition: str, seg: str) -> str:
    rp = _path.ResultPaths(namecode)
    name = rp.trc_name(condition, seg)
    section = rp.seg_to_section(seg)
    cands = [
        os.path.join(root, rp.protocol, rp.sub_label, condition, section, "Markers", name)
        for root in opensim_roots()
    ]
    hit = _first_existing_file(cands)
    if hit is None:
        raise FileNotFoundError(
            f"Segment TRC not found for {namecode} {condition} {seg}. Tried:\n  "
            + "\n  ".join(cands)
        )
    return hit


def heavyhand_extload_path(namecode: str, condition: str, seg: str) -> str:
    rp = _path.ResultPaths(namecode)
    name = rp.extload_name(condition, seg, "HeavyHand")
    section = rp.seg_to_section(seg)
    cands = [
        os.path.join(root, rp.protocol, rp.sub_label, condition, section, "ExtLoad", name)
        for root in opensim_roots()
    ]
    hit = _first_existing_file(cands)
    if hit is None:
        raise FileNotFoundError(
            f"HeavyHand ExtLoad missing for {namecode} {condition} {seg}. Tried:\n  "
            + "\n  ".join(cands)
        )
    return hit


def boxwrench_extload_path(namecode: str, condition: str, seg: str) -> str:
    """Write ExtLoad_BoxWrench next to the resolved HeavyHand MOT."""
    hh = heavyhand_extload_path(namecode, condition, seg)
    rp = _path.ResultPaths(namecode)
    return os.path.join(
        os.path.dirname(hh),
        rp.extload_name(condition, seg, cfg.APP_NAME),
    )


def ricto_timeseries_path(namecode: str, condition: str, seg: str) -> Optional[str]:
    """PATH_RULE layout first, then legacy Dropbox ``Analysis/RiCTO/…`` layout."""
    rp = _path.ResultPaths(namecode)
    fname = f"{rp.sub_label}_{condition}_{seg}_RiCTO_timeseries.csv"
    cands = [
        os.path.join(rp.ricto_timeseries_dir(condition), fname),
        os.path.join(
            _path.ANALYSIS_DIR,
            "RiCTO",
            rp.protocol,
            rp.sub_label,
            condition,
            "timeseries",
            fname,
        ),
        os.path.join(
            _path.COWORK_ROOT_DIR,
            "Analysis",
            "RiCTO",
            rp.protocol,
            rp.sub_label,
            condition,
            "timeseries",
            fname,
        ),
        os.path.join(
            _path.COWORK_ROOT_DIR,
            "Analysis",
            rp.protocol,
            "RiCTO",
            "TimeSeries",
            rp.sub_label,
            condition,
            fname,
        ),
    ]
    return _first_existing_file(cands)


def load_ik_paths(namecode: str, condition: str, seg: str) -> dict[str, str]:
    rp = _path.ResultPaths(namecode)
    folder = section_folder(namecode, condition, seg, cfg.LOAD_IK_FOLDER)
    setup = os.path.join(folder, f"SETUP_IK_{condition}_{seg}_{cfg.LOAD_FOLDER_SUFFIX}.xml")
    mot = os.path.join(
        folder, f"{rp.sub_label}_{condition}_{seg}_{cfg.LOAD_FOLDER_SUFFIX}_IK.mot"
    )
    return {"dir": folder, "setup": setup, "mot": mot}


def load_bk_paths(namecode: str, condition: str, seg: str) -> dict[str, str]:
    rp = _path.ResultPaths(namecode)
    folder = section_folder(namecode, condition, seg, cfg.LOAD_BK_FOLDER)
    prefix = f"{rp.sub_label}_{condition}_{seg}_{cfg.LOAD_FOLDER_SUFFIX}"
    setup = os.path.join(folder, f"SETUP_BK_{condition}_{seg}_{cfg.LOAD_FOLDER_SUFFIX}.xml")
    return {
        "dir": folder,
        "setup": setup,
        "prefix": prefix,
        "vel": os.path.join(folder, f"{prefix}_BodyKinematics_vel_global.sto"),
        "pos": os.path.join(folder, f"{prefix}_BodyKinematics_pos_global.sto"),
    }


def load_states_paths(namecode: str, condition: str, seg: str) -> dict[str, str]:
    rp = _path.ResultPaths(namecode)
    folder = section_folder(namecode, condition, seg, cfg.LOAD_STATES_FOLDER)
    prefix = f"{rp.sub_label}_{condition}_{seg}_{cfg.LOAD_FOLDER_SUFFIX}"
    setup = os.path.join(
        folder, f"SETUP_States_{condition}_{seg}_{cfg.LOAD_FOLDER_SUFFIX}.xml"
    )
    return {
        "dir": folder,
        "setup": setup,
        "prefix": prefix,
        "states": os.path.join(folder, f"{prefix}_StatesReporter_states.sto"),
    }


def analysis_forces_csv(namecode: str, condition: str, seg: str) -> str:
    rp = _path.ResultPaths(namecode)
    return os.path.join(
        rp.boxwrench_timeseries_dir(condition),
        f"{rp.sub_label}_{condition}_{seg}_BoxWrench_forces.csv",
    )


def rigidbody_csv(namecode: str, condition: str) -> Optional[str]:
    p = os.path.join(
        _path.DATA_DIR, namecode, "RigidBody", f"{condition}_rigidbody.csv"
    )
    return p if os.path.isfile(p) else None

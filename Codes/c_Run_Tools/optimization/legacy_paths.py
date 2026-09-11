"""Legacy OneCycle (c_AddBio_Continous) path helpers for RiCTO.

Kept out of ``Codes/PATH_RULE.py`` so the modern ResultPaths API stays the
source of truth. Used only by ``run_ricto.py --legacy`` / ``validate_ricto.py``.
"""

from __future__ import annotations

import os
from typing import Optional

import PATH_RULE as _path


def legacy_opensim_root() -> str:
    """Prefer Dropbox cowork tree; fall back to repo OpenSim/_Main_/c_AddBio_Continous."""
    candidates = [
        os.path.join(_path.COWORK_ROOT_DIR, "OpenSim", "_Main_", "c_AddBio_Continous"),
        os.path.join(_path.ROOT_DIR, "OpenSim", "_Main_", "c_AddBio_Continous"),
        os.path.join(_path.ROOT_DIR, "OpenSim", "_Main_"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def legacy_onecycle_dirs(
    sub: str = "SUB1",
    trial_folder: str = "trial15_10_1",
    app: str = "APP2_OneCycle",
) -> dict:
    root = legacy_opensim_root()
    trial = os.path.join(root, sub, app, trial_folder)
    return {
        "root": root,
        "trial": trial,
        "bk": os.path.join(trial, "BK_Results"),
        "bk_postsim": os.path.join(trial, "BK_Results", "PostSim"),
        "so": os.path.join(trial, "SO_Results"),
        "so_postsim": os.path.join(trial, "SO_Results", "PostSim"),
        "id": os.path.join(trial, "ID_Results"),
        "extload_dir": os.path.join(root, sub, "OneCycle_TrcMot"),
        "analysis": _path._ensure_dir(
            _path.ANALYSIS_DIR, "RiCTO", "Symmetric", sub, trial_folder
        ),
    }


def legacy_extload_mot_path(
    *,
    kg_bpm: str,
    trial_num: int,
    task_num: int,
    mode: str,
    sub: str = "SUB1",
    app_suffix: str = "APP2",
) -> str:
    """pre → ``_estimated_original``, post → ``_RiCTO-corrected``."""
    dirs = legacy_onecycle_dirs(sub=sub)
    base = f"{kg_bpm}_trial{trial_num}_12sec_{task_num}_ExtLoad{app_suffix}"
    if mode in ("pre", "original", "preRiCTO"):
        suffix = "_estimated_original"
    elif mode in ("post", "corrected", "postRiCTO"):
        suffix = "_RiCTO-corrected"
    else:
        raise ValueError(f"Unknown ExtLoad mode: {mode!r}")
    return os.path.join(dirs["extload_dir"], f"{base}{suffix}.mot")

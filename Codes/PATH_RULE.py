"""Path rules for BOX OpenSim process and Analysis outputs.

Provides a thin, workspace-relative path API used by
``Codes/c_Run_Tools/optimization`` (RiCTO) and other pipeline modules.

Layout preferences (first existing wins for OpenSim roots):

1. ``OpenSim_Process/_Main_``  (modern Asymmetric tree)
2. ``OpenSim/_Main_/c_AddBio_Continous``  (legacy Symmetric OneCycle tree)

Analysis outputs always go under ``Analysis/`` at the repo root.
"""

from __future__ import annotations

import os
from typing import Optional

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CODE_DIR)

ANALYSIS_DIR = os.path.join(ROOT_DIR, "Analysis")
os.makedirs(ANALYSIS_DIR, exist_ok=True)

# Optional cowork mirror (Dropbox). Empty / missing is fine in cloud VMs.
COWORK_ROOT_DIR = os.environ.get("BOX_COWORK_ROOT", r"E:\Dropbox\SEL\BOX")


def _ensure_dir(*parts: str) -> str:
    d = os.path.join(*parts)
    os.makedirs(d, exist_ok=True)
    return d


def resolve_opensim_main() -> str:
    """Return the preferred OpenSim process root that exists on disk."""
    candidates = [
        os.path.join(ROOT_DIR, "OpenSim_Process", "_Main_"),
        os.path.join(ROOT_DIR, "OpenSim", "_Main_", "c_AddBio_Continous"),
        os.path.join(ROOT_DIR, "OpenSim", "_Main_"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    # Default to modern layout even if not created yet.
    return candidates[0]


OPENSIM_DIR = resolve_opensim_main()


class ResultPaths:
    """Subject-level path builder.

    Works for both modern ``Asymmetric/SUBn/...`` trees and legacy
    ``SUBn/APP2_OneCycle/...`` layouts. Callers pass ``protocol`` explicitly
    when the modern tree is used; leave empty for legacy flat SUB folders.
    """

    def __init__(
        self,
        sub_label: str,
        *,
        protocol: str = "",
        namecode: str = "",
    ):
        self.sub_label = sub_label  # e.g. "SUB1"
        self.protocol = protocol    # e.g. "Asymmetric" or ""
        self.namecode = namecode

        if protocol:
            self.sub_dir = _ensure_dir(OPENSIM_DIR, protocol, sub_label)
        else:
            self.sub_dir = _ensure_dir(OPENSIM_DIR, sub_label)

        self.model_dir = _ensure_dir(self.sub_dir, "Model_osim")

    def analysis_dir(self, *parts: str) -> str:
        """``Analysis/RiCTO/<protocol>/<SUB>/...`` (protocol may be empty)."""
        base = [ANALYSIS_DIR, "RiCTO"]
        if self.protocol:
            base.append(self.protocol)
        base.append(self.sub_label)
        base.extend(parts)
        return _ensure_dir(*base)

    def for_condition(self, cond: str) -> "ConditionPaths":
        return ConditionPaths(self, cond)


class ConditionPaths:
    """Condition-scoped paths (modern or legacy)."""

    def __init__(self, parent: ResultPaths, cond: str):
        self._p = parent
        self.cond = cond
        self.cond_dir = _ensure_dir(parent.sub_dir, cond)

    @property
    def sub_label(self) -> str:
        return self._p.sub_label

    def analysis_dir(self, *parts: str) -> str:
        return self._p.analysis_dir(self.cond, *parts)

    # ── Modern ExtLoad / BK / ID helpers ──────────────────────────

    def section_dir(self, section: str) -> str:
        return _ensure_dir(self.cond_dir, section)

    def extload_dir(self, section: str) -> str:
        return _ensure_dir(self.section_dir(section), "ExtLoad")

    def bk_dir(self, section: str) -> str:
        return _ensure_dir(self.section_dir(section), "BK")

    def id_dir(self, section: str, app: str = "HeavyHand") -> str:
        return _ensure_dir(self.section_dir(section), f"ID_{app}")

    def so_dir(self, section: str, app: str) -> str:
        return _ensure_dir(self.section_dir(section), f"SO_{app}")

    def extload_name(self, seg: str, app: str) -> str:
        return f"{self.sub_label}_{self.cond}_{seg}_ExtLoad_{app}.mot"

    def extload_path(self, seg: str, app: str) -> str:
        # seg like "1AB" → section "AB"
        section = "".join(ch for ch in seg if ch.isalpha()) or seg
        return os.path.join(self.extload_dir(section), self.extload_name(seg, app))

    def bk_name(self, seg: str, bk_type: str) -> str:
        return f"{self.sub_label}_{self.cond}_{seg}_BodyKinematics_{bk_type}.sto"

    def bk_path(self, seg: str, bk_type: str) -> str:
        section = "".join(ch for ch in seg if ch.isalpha()) or seg
        return os.path.join(self.bk_dir(section), self.bk_name(seg, bk_type))

    def id_name(self, seg: str, app: str = "HeavyHand") -> str:
        return f"{self.sub_label}_{self.cond}_{seg}_{app}_InverseDynamics.sto"

    def id_path(self, seg: str, app: str = "HeavyHand") -> str:
        section = "".join(ch for ch in seg if ch.isalpha()) or seg
        return os.path.join(self.id_dir(section, app), self.id_name(seg, app))

    def so_name(self, seg: str, app: str, so_type: str = "force") -> str:
        return f"{self.sub_label}_{self.cond}_{seg}_{app}_StaticOptimization_{so_type}.sto"

    def so_path(self, seg: str, app: str, so_type: str = "force") -> str:
        section = "".join(ch for ch in seg if ch.isalpha()) or seg
        return os.path.join(self.so_dir(section, app), self.so_name(seg, app, so_type))

    # ── RiCTO analysis artifacts ──────────────────────────────────

    def ricto_summary_path(self) -> str:
        return os.path.join(
            self.analysis_dir(),
            f"{self.sub_label}_{self.cond}_RiCTO_summary.csv",
        )

    def ricto_timeseries_path(self, seg: str) -> str:
        return os.path.join(
            self.analysis_dir("timeseries"),
            f"{self.sub_label}_{self.cond}_{seg}_RiCTO_timeseries.csv",
        )

    def ricto_plot_path(self, seg: str, tag: str = "overview") -> str:
        return os.path.join(
            self.analysis_dir("plots"),
            f"{self.sub_label}_{self.cond}_{seg}_RiCTO_{tag}.png",
        )


# ── Legacy OneCycle helpers (Symmetric / c_AddBio_Continous) ──────

def legacy_onecycle_dirs(
    sub: str = "SUB1",
    trial_folder: str = "trial15_10_1",
    app: str = "APP2_OneCycle",
) -> dict:
    """Return common legacy paths under ``OpenSim/_Main_/c_AddBio_Continous``."""
    root = resolve_opensim_main()
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
        "analysis": _ensure_dir(ANALYSIS_DIR, "RiCTO", "Symmetric", sub, trial_folder),
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

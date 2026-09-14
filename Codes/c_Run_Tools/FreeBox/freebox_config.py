"""FreeBox configuration constants and policies.

Code / PATH_RULE / file names use ``FreeBox``.
Document-facing labels (figure legends, titles, captions) use ``LoadShare``.
"""

from __future__ import annotations

import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
_CODES = os.path.dirname(os.path.dirname(_THIS))
if _CODES not in sys.path:
    sys.path.insert(0, _CODES)

import PATH_RULE as _path  # noqa: E402

APP_NAME: str = "FreeBox"
# Manuscript / plot legend label (not used in PATH_RULE paths).
DISPLAY_NAME: str = "LoadShare"

# ExtLoad hand mapping (same as RiCTO / SETUP XML): plate 3=L, 4=R
HAND_L_FORCE_PREFIX = "hand_force3"
HAND_R_FORCE_PREFIX = "hand_force4"
HAND_L_TORQUE_PREFIX = "hand_torque3"
HAND_R_TORQUE_PREFIX = "hand_torque4"

# Template MOT keeps measured GRF; hand columns replaced by FreeBox.
EXTLOAD_TEMPLATE_APP: str = "HeavyHand"

# Coupling to RiCTO timing (not MeasuredEHF).
# "smooth" → post-style weight; "rect" → pre-style hard window.
RICTO_WEIGHT_MODE: str = "smooth"  # "smooth" | "rect"

# Hand torques written as zeros (ExtForceGen policy retained).
FORCE_ZERO_HAND_TORQUE: bool = True

# Physics
GRAVITY_Y: float = -9.80660
GRAVITY_VEC = (0.0, GRAVITY_Y, 0.0)

# Default box models live under OpenSim_Process/Model/Design_Box (not package models/).
DEFAULT_BOX_OSIM: str = _path.freebox_box_osim_path(with_markers=False)
DEFAULT_BOX_WITH_MARKERS_OSIM: str = _path.freebox_box_osim_path(with_markers=True)
DEFAULT_BOX_BODY_NAME: str = "BOX"
# Reference mass in BOX.osim (~15.02 kg CAD). Condition kg scales inertia.
REF_BOX_MASS_KG: float = 15.028443336486816

# Free-box Analyze (vendor LoadBK/LoadStates used 3 Hz; human BK uses 6 Hz).
LOAD_ANALYZE_CUTOFF_HZ: float = 6.0
LOAD_IK_MARKER_WEIGHT: float = 1.0
# OpenSim_Process folder suffixes (parallel to IK / IK_AddBox).
LOAD_IK_FOLDER: str = "IK_Load"
LOAD_BK_FOLDER: str = "BK_Load"
LOAD_STATES_FOLDER: str = "States_Load"
LOAD_FOLDER_SUFFIX: str = "Load"  # file-name tag: …_Load_IK.mot

# Real-data sample defaults (not 260512_HSH).
SAMPLE_NAMECODE: str = "260526_PJH"
SAMPLE_CONDITION: str = "7kg_10bpm"
SAMPLE_SEGMENT: str = "1AB"

# Corner markers used for free-box IK (handles optional / often absent in TRC).
BOX_IK_MARKER_NAMES: tuple[str, ...] = (
    "LTA_BOX",
    "LTP_BOX",
    "LBA_BOX",
    "LBP_BOX",
    "RTA_BOX",
    "RTP_BOX",
    "RBA_BOX",
    "RBP_BOX",
)

# Handle / COP bounds in **CAD / BOX body** frame (m), relative to box center.
# ML along body **Z** (±~0.160 m) — ADDBOX / STL import. Motive D3/D4 use ±X
# in the rigid-body frame; see freebox_markers.py for both.
HANDLE_L_NOM: tuple[float, float, float] = (0.0, 0.0158, -0.16001)
HANDLE_R_NOM: tuple[float, float, float] = (0.0, 0.0158, 0.16007)
HANDLE_Z_NOM: float = 0.5 * (abs(HANDLE_L_NOM[2]) + abs(HANDLE_R_NOM[2]))
HANDLE_X_NOM: float = HANDLE_Z_NOM  # alias: ML half-width
COP_DELTA_XYZ: float = 0.05  # half-range for COP search (±) about handle nom
FORCE_BOUND_N: float = 100.0  # per-axis force bound in box frame (vendor)

# Allocation optimizer
ALLOC_TOL: float = 1.0e-6
ALLOC_MAXITER: int = 200

# Rotation: OpenSim BodyKinematics body-fixed XYZ (deg) → R_body_to_ground.
# Composition Rx@Ry@Rz matches historical RotMat; OpenSim Rotation is SoT — see freebox_rotation.
ROTATION_MODE: str = "body_fixed_xyz_deg"  # see freebox_rotation.py

PIPELINE_OPT_IN: bool = True

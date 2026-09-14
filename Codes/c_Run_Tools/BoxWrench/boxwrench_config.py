"""BoxWrench configuration constants and policies.

App / folder name is ``BoxWrench`` (not APP5). Literature reference only:
Akhavanfar et al. 2022 Approach 5.
"""

from __future__ import annotations

APP_NAME: str = "BoxWrench"

# ExtLoad hand mapping (same as RiCTO / SETUP XML): plate 3=L, 4=R
HAND_L_FORCE_PREFIX = "hand_force3"
HAND_R_FORCE_PREFIX = "hand_force4"
HAND_L_TORQUE_PREFIX = "hand_torque3"
HAND_R_TORQUE_PREFIX = "hand_torque4"

# Template MOT keeps measured GRF; hand columns replaced by BoxWrench.
EXTLOAD_TEMPLATE_APP: str = "HeavyHand"

# Coupling to RiCTO timing (not MeasuredEHF).
# "smooth" → post-style weight; "rect" → pre-style hard window.
RICTO_WEIGHT_MODE: str = "smooth"  # "smooth" | "rect"

# Torque policy until Approach-5 vendor code is reviewed.
# True: write zeros (RiCTO / HeavyHand default). False: allow vendor moments.
FORCE_ZERO_HAND_TORQUE: bool = True

# Physics placeholders (override from box .osim when available).
GRAVITY_Y: float = -9.80660
GRAVITY_VEC = (0.0, GRAVITY_Y, 0.0)

# Pipeline: opt-in app (not added to default protocol APPs).
PIPELINE_OPT_IN: bool = True

# Blocked integration message shared by stubs.
BLOCKED_REASON: str = (
    "BoxWrench numerical path is blocked: Approach-5 Python sources and/or "
    "box .osim are not present in the workspace. Scaffolding only — see "
    "Codes/c_Run_Tools/BoxWrench/BOXWRENCH_PLAN.md."
)

# Expected vendor drop locations (documentation; not required to exist yet).
VENDOR_SOURCE_HINTS: tuple[str, ...] = (
    "Codes/c_Run_Tools/BoxWrench/_vendor/",  # preferred after adaptation
    "vendor/Approach5/",
    "Approach5/",
)
BOX_OSIM_HINTS: tuple[str, ...] = (
    "OpenSim_Process/Model/*Box*.osim",
    "Codes/c_Run_Tools/BoxWrench/models/*.osim",
)

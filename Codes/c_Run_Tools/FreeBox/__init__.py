"""FreeBox: free-joint box dynamics → L/R ExtLoad, gated by RiCTO timing.

Document-facing label: LoadShare (``DISPLAY_NAME``).
"""

from .freebox_config import (
    APP_NAME,
    DISPLAY_NAME,
    HANDLE_L_NOM,
    HANDLE_R_NOM,
    HANDLE_X_NOM,
    SAMPLE_CONDITION,
    SAMPLE_NAMECODE,
    SAMPLE_SEGMENT,
)
from .freebox_allocate import allocate_hand_loads
from .freebox_extload import build_freebox_extload, write_freebox_mot
from .freebox_inertia import load_box_props_for_condition
from .freebox_kinematics import compute_box_com_motion, compute_box_net_wrench
from .freebox_markers import handle_centers_from_box_center, markers_in_left_half_frame

__all__ = [
    "APP_NAME",
    "DISPLAY_NAME",
    "HANDLE_L_NOM",
    "HANDLE_R_NOM",
    "HANDLE_X_NOM",
    "SAMPLE_NAMECODE",
    "SAMPLE_CONDITION",
    "SAMPLE_SEGMENT",
    "allocate_hand_loads",
    "build_freebox_extload",
    "write_freebox_mot",
    "load_box_props_for_condition",
    "compute_box_com_motion",
    "compute_box_net_wrench",
    "handle_centers_from_box_center",
    "markers_in_left_half_frame",
]

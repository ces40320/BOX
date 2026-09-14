"""Box pose → COM linear/angular kinematics for BoxWrench.

Stub only. Will reuse repo parsers / ``ricto_ehf.second_derivative`` once
Approach-5 kinematics inputs and the box model are available.

ASSUMPTION (future): OpenSim ground frame with +Y vertical; rotation
convention must be documented when vendor ``RotMat`` is replaced.
"""

from __future__ import annotations

from typing import Any, Dict

from .boxwrench_config import BLOCKED_REASON


def compute_box_com_motion(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Return box COM position, velocity, acceleration, ω, α over time.

    Raises
    ------
    NotImplementedError
        Always, until vendor Approach-5 kinematics + box ``.osim`` arrive.
    """
    raise NotImplementedError(BLOCKED_REASON)


def compute_box_net_wrench(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Newton–Euler net force/moment at box COM from kinematics + inertia.

    Raises
    ------
    NotImplementedError
        Always in this scaffolding pass.
    """
    raise NotImplementedError(BLOCKED_REASON)

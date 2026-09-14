"""BoxWrench: Approach-5-inspired box wrench → L/R ExtLoad (RiCTO-gated).

Full numerical integration is blocked until Approach-5 sources and the box
``.osim`` are provided. See ``BOXWRENCH_PLAN.md``.
"""

from .boxwrench_config import APP_NAME, BLOCKED_REASON

__all__ = ["APP_NAME", "BLOCKED_REASON"]

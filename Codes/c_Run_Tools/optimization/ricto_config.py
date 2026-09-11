"""RiCTO configuration constants and policies."""

from __future__ import annotations

# ── Physics ──────────────────────────────────────────────────
GRAVITY_Y: float = -9.80660
GRAVITY_VEC = (0.0, GRAVITY_Y, 0.0)
MASS_SPLIT_ALPHA: float = 0.5  # equal L/R mass share (ASSUMPTION)

# ── Hand column mapping (OpenSim ExtLoad convention) ─────────
# plate 3 = left hand, plate 4 = right hand
HAND_L_FORCE_PREFIX = "hand_force3"
HAND_R_FORCE_PREFIX = "hand_force4"
HAND_L_TORQUE_PREFIX = "hand_torque3"
HAND_R_TORQUE_PREFIX = "hand_torque4"

# ── Acceleration / EHF ───────────────────────────────────────
ACC_SOURCE: str = "pos_global"  # never use BK acc_global by default
ACC_LOWPASS_HZ: float = 6.0     # Butterworth before 2nd derivative
ACC_FILTER_ORDER: int = 4
A_MAX_QC: float = 30.0          # m/s^2 QC threshold only (despike OFF)
DESPIKE: bool = False

# ── Residual / baseline ──────────────────────────────────────
RESIDUAL_SOURCE_PRIMARY: str = "id"   # "id" | "so"
RESIDUAL_ID_COL: str = "pelvis_ty_force"
RESIDUAL_SO_COL: str = "residual_pelvis_ty"
BASELINE_MODE: str = "theory"         # "theory" | "edge_mean" | "early_mean"
BASELINE_EDGE_SEC: float = 0.5
BASELINE_WARN_FRAC: float = 0.15      # |B_edge/B_theory - 1| warning

# ── Optimization bounds / init ───────────────────────────────
D_LO: float = 0.05
D_HI: float = 0.80
DELTA_MIN: float = 0.10               # t2 = t1 + d1 + delta
T1_PAD_LO: float = 0.05
T1_PAD_HI: float = 0.50
CONTACT_FRAC_OF_B: float = 0.50       # residual < frac*B → non-contact? wait
# residual high when unloaded (HeavyHand mass always on); contact lowers residual
# → contact mask: residual < CONTACT_FRAC_OF_B * B
INIT_D: float = 0.20
MIN_CONTACT_DUR: float = 0.30

# ── Solvers ──────────────────────────────────────────────────
DEFAULT_SOLVER: str = "least_squares"  # nm | least_squares | de | grid_local
SOLVERS = ("nm", "least_squares", "de", "grid_local")
NM_MAXITER: int = 5000
LS_LOSS: str = "soft_l1"
DE_MAXITER: int = 80
DE_POPSIZE: int = 15
GRID_T1_N: int = 12
GRID_T2_N: int = 12

# ── ExtLoad write policy ─────────────────────────────────────
# Template: HeavyHand MOT (GRF kept). Hand forces from kinematics.
# Never copy MeasuredEHF hand columns into pre/postRiCTO MOT.
EXTLOAD_TEMPLATE_APP: str = "HeavyHand"
FORCE_ZERO_HAND_TORQUE: bool = True
APPLY_AXES: tuple[str, ...] = ("vx", "vy", "vz")  # all three

# ── Modes ────────────────────────────────────────────────────
MODE_PRE: str = "pre"    # rect weight → preRiCTO / estimated_original
MODE_POST: str = "post"  # smooth weight → postRiCTO / RiCTO-corrected

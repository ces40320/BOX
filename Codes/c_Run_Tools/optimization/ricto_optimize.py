"""RiCTO residual-minimizing optimization (weight curves + solvers)."""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import differential_evolution, least_squares, minimize

from . import ricto_config as cfg


def smoothstep_ramp(t: np.ndarray, t_start: float, duration: float) -> np.ndarray:
    if duration < 0.01:
        return np.where(t >= t_start, 1.0, 0.0)
    tau = np.clip((t - t_start) / duration, 0.0, 1.0)
    return 3.0 * tau**2 - 2.0 * tau**3


def smooth_weight_curve(t, t1, d1, t2, d2) -> np.ndarray:
    return np.clip(smoothstep_ramp(t, t1, d1) - smoothstep_ramp(t, t2, d2), 0.0, 1.0)


def rectangle_weight_curve(t, t1, d1, t2, d2) -> np.ndarray:
    t_off = t2 + d2
    return np.where((t >= t1) & (t <= t_off), 1.0, 0.0)


def baseline_theory(box_mass_kg: float, gravity_y: float = cfg.GRAVITY_Y) -> float:
    """HeavyHand always-on mass appears as +m_box*|g| in pelvis_ty residual when unloaded."""
    return float(abs(box_mass_kg * gravity_y))


def baseline_edge_mean(
    time_s: np.ndarray,
    residual: np.ndarray,
    edge_sec: float = cfg.BASELINE_EDGE_SEC,
) -> float:
    t = np.asarray(time_s, float)
    r = np.asarray(residual, float)
    t0, t1 = float(t[0]), float(t[-1])
    mask = (t <= t0 + edge_sec) | (t >= t1 - edge_sec)
    if not np.any(mask):
        return float(np.mean(r))
    return float(np.mean(r[mask]))


def baseline_early_mean(
    time_s: np.ndarray,
    residual: np.ndarray,
    early_sec: float = cfg.BASELINE_EDGE_SEC,
) -> float:
    t = np.asarray(time_s, float) - float(time_s[0])
    r = np.asarray(residual, float)
    mask = t < early_sec
    if not np.any(mask):
        return float(r[0])
    return float(np.mean(r[mask]))


def resolve_baseline(
    time_s: np.ndarray,
    residual: np.ndarray,
    box_mass_kg: float,
    mode: str = cfg.BASELINE_MODE,
) -> Dict[str, float]:
    b_th = baseline_theory(box_mass_kg)
    b_edge = baseline_edge_mean(time_s, residual)
    b_early = baseline_early_mean(time_s, residual)
    if mode == "theory":
        b = b_th
    elif mode == "edge_mean":
        b = b_edge
    elif mode == "early_mean":
        b = b_early
    else:
        raise ValueError(f"Unknown baseline mode: {mode!r}")
    ratio = b_edge / b_th if b_th > 0 else np.nan
    warn = abs(ratio - 1.0) > cfg.BASELINE_WARN_FRAC if np.isfinite(ratio) else True
    return {
        "B": float(b),
        "B_theory": float(b_th),
        "B_edge": float(b_edge),
        "B_early": float(b_early),
        "B_edge_over_theory": float(ratio),
        "warn_baseline": bool(warn),
        "mode": mode,
    }


def _bounds_native(t0: float, t_end: float) -> Dict[str, Tuple[float, float]]:
    t1_lo = t0 + cfg.T1_PAD_LO
    t1_hi = max(t1_lo + 0.2, t_end - cfg.T1_PAD_HI)
    return {
        "t1": (t1_lo, t1_hi),
        "d": (cfg.D_LO, cfg.D_HI),
        "delta": (cfg.DELTA_MIN, max(cfg.DELTA_MIN + 0.1, t_end - t0)),
    }


def pack_theta(t1: float, d1: float, t2: float, d2: float) -> np.ndarray:
    return np.array([t1, d1, t2, d2], dtype=float)


def reparam_to_theta(u: Sequence[float]) -> np.ndarray:
    """u = [t1, d1, delta, d2] → θ = [t1,d1,t2,d2] with t2 = t1+d1+delta."""
    t1, d1, delta, d2 = map(float, u)
    return np.array([t1, d1, t1 + d1 + delta, d2], dtype=float)


def theta_to_reparam(theta: Sequence[float]) -> np.ndarray:
    t1, d1, t2, d2 = map(float, theta)
    return np.array([t1, d1, max(cfg.DELTA_MIN, t2 - t1 - d1), d2], dtype=float)


def residual_vector(
    theta: Sequence[float],
    time_s: np.ndarray,
    residual: np.ndarray,
    baseline: float,
) -> np.ndarray:
    t1, d1, t2, d2 = theta
    w = smooth_weight_curve(time_s, t1, d1, t2, d2)
    return residual - baseline * (1.0 - w)


def sse_cost(theta, time_s, residual, baseline) -> float:
    return float(np.sum(residual_vector(theta, time_s, residual, baseline) ** 2))


def detect_init_guess(
    time_s: np.ndarray,
    residual: np.ndarray,
    baseline: float,
) -> np.ndarray:
    """Longest low-residual interval → contact window init (ricto_core style)."""
    t = np.asarray(time_s, float)
    r = np.asarray(residual, float)
    # unloaded → high residual (~B); contact → residual drops
    in_contact = r < cfg.CONTACT_FRAC_OF_B * baseline
    d = np.diff(in_contact.astype(int), prepend=0, append=0)
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    best = (0, 0, 0.0)
    for s, e in zip(starts, ends):
        e = min(e, len(t) - 1)
        dur = float(t[e] - t[s])
        if dur > best[2]:
            best = (s, e, dur)
    t0, t_end = float(t[0]), float(t[-1])
    if best[2] >= cfg.MIN_CONTACT_DUR:
        t1i = float(t[best[0]])
        t2i = float(t[best[1]])
    else:
        span = t_end - t0
        t1i, t2i = t0 + 0.25 * span, t0 + 0.75 * span
    d = cfg.INIT_D
    # ensure ordering
    if t1i + d >= t2i:
        t2i = t1i + d + cfg.DELTA_MIN
    return pack_theta(t1i, d, t2i, d)


def _clip_theta(theta: np.ndarray, t0: float, t_end: float) -> np.ndarray:
    t1, d1, t2, d2 = theta
    b = _bounds_native(t0, t_end)
    t1 = float(np.clip(t1, *b["t1"]))
    d1 = float(np.clip(d1, *b["d"]))
    d2 = float(np.clip(d2, *b["d"]))
    t2 = float(np.clip(t2, t1 + d1 + cfg.DELTA_MIN, t_end - 0.02))
    return pack_theta(t1, d1, t2, d2)


def _solve_nm(time_s, residual, baseline, x0) -> Dict:
    t0, t_end = float(time_s[0]), float(time_s[-1])

    def obj(th):
        t1, d1, t2, d2 = th
        if d1 < cfg.D_LO or d2 < cfg.D_LO or d1 > cfg.D_HI or d2 > cfg.D_HI:
            return 1e9
        if t1 < t0 + cfg.T1_PAD_LO or t2 > t_end - 0.02 or t1 + d1 >= t2:
            return 1e9
        return sse_cost(th, time_s, residual, baseline)

    res = minimize(
        obj,
        x0=np.asarray(x0, float),
        method="Nelder-Mead",
        options={"maxiter": cfg.NM_MAXITER, "xatol": 1e-4, "fatol": 1e-4},
    )
    th = _clip_theta(res.x.astype(float), t0, t_end)
    return {
        "params": th,
        "cost": sse_cost(th, time_s, residual, baseline),
        "success": bool(res.success),
        "nfev": int(getattr(res, "nfev", -1)),
        "message": str(getattr(res, "message", "")),
        "solver": "nm",
    }


def _solve_least_squares(time_s, residual, baseline, x0) -> Dict:
    t0, t_end = float(time_s[0]), float(time_s[-1])
    b = _bounds_native(t0, t_end)
    u0 = theta_to_reparam(x0)
    u0[0] = np.clip(u0[0], *b["t1"])
    u0[1] = np.clip(u0[1], *b["d"])
    u0[2] = np.clip(u0[2], *b["delta"])
    u0[3] = np.clip(u0[3], *b["d"])
    lo = np.array([b["t1"][0], b["d"][0], b["delta"][0], b["d"][0]])
    hi = np.array([b["t1"][1], b["d"][1], b["delta"][1], b["d"][1]])

    def fun(u):
        return residual_vector(reparam_to_theta(u), time_s, residual, baseline)

    res = least_squares(fun, u0, bounds=(lo, hi), loss=cfg.LS_LOSS, max_nfev=8000)
    th = _clip_theta(reparam_to_theta(res.x), t0, t_end)
    return {
        "params": th,
        "cost": sse_cost(th, time_s, residual, baseline),
        "success": bool(res.success),
        "nfev": int(res.nfev),
        "message": str(res.message),
        "solver": "least_squares",
    }


def _solve_de(time_s, residual, baseline, x0=None) -> Dict:
    t0, t_end = float(time_s[0]), float(time_s[-1])
    b = _bounds_native(t0, t_end)
    bounds = [b["t1"], b["d"], b["delta"], b["d"]]

    def obj(u):
        return sse_cost(reparam_to_theta(u), time_s, residual, baseline)

    res = differential_evolution(
        obj,
        bounds=bounds,
        maxiter=cfg.DE_MAXITER,
        popsize=cfg.DE_POPSIZE,
        polish=True,
        seed=0,
    )
    th = _clip_theta(reparam_to_theta(res.x), t0, t_end)
    return {
        "params": th,
        "cost": sse_cost(th, time_s, residual, baseline),
        "success": bool(res.success),
        "nfev": int(res.nfev),
        "message": str(res.message),
        "solver": "de",
    }


def _solve_grid_local(time_s, residual, baseline, x0=None) -> Dict:
    t0, t_end = float(time_s[0]), float(time_s[-1])
    b = _bounds_native(t0, t_end)
    d_fixed = cfg.INIT_D
    best_u = None
    best_c = np.inf
    t1_grid = np.linspace(b["t1"][0], b["t1"][1], cfg.GRID_T1_N)
    for t1 in t1_grid:
        t2_lo = t1 + d_fixed + cfg.DELTA_MIN
        if t2_lo >= t_end - 0.05:
            continue
        t2_grid = np.linspace(t2_lo, t_end - 0.05, cfg.GRID_T2_N)
        for t2 in t2_grid:
            th = pack_theta(t1, d_fixed, t2, d_fixed)
            c = sse_cost(th, time_s, residual, baseline)
            if c < best_c:
                best_c = c
                best_u = theta_to_reparam(th)
    if best_u is None:
        best_u = theta_to_reparam(detect_init_guess(time_s, residual, baseline))
    # local polish with NM on reparam→theta
    th0 = reparam_to_theta(best_u)
    local = _solve_nm(time_s, residual, baseline, th0)
    local["solver"] = "grid_local"
    local["grid_cost"] = float(best_c)
    return local


_SOLVER_FN: Dict[str, Callable] = {
    "nm": _solve_nm,
    "least_squares": _solve_least_squares,
    "de": _solve_de,
    "grid_local": _solve_grid_local,
}


def optimize_ricto(
    time_s: np.ndarray,
    residual: np.ndarray,
    box_mass_kg: float,
    *,
    solver: str = cfg.DEFAULT_SOLVER,
    baseline_mode: str = cfg.BASELINE_MODE,
) -> Dict:
    """Optimize (t1,d1,t2,d2). Returns params, weights, baseline pack, solver info."""
    t = np.asarray(time_s, float)
    r = np.asarray(residual, float)
    if solver not in _SOLVER_FN:
        raise ValueError(f"Unknown solver {solver!r}. Choose from {cfg.SOLVERS}")

    bpack = resolve_baseline(t, r, box_mass_kg, mode=baseline_mode)
    B = bpack["B"]
    x0 = detect_init_guess(t, r, B)
    sol = _SOLVER_FN[solver](t, r, B, x0)
    th = sol["params"]
    t1, d1, t2, d2 = th
    return {
        **sol,
        **bpack,
        "params": th,
        "t1": float(t1),
        "d1": float(d1),
        "t2": float(t2),
        "d2": float(d2),
        "time": t,
        "residual": r,
        "smooth_w": smooth_weight_curve(t, t1, d1, t2, d2),
        "rect_w": rectangle_weight_curve(t, t1, d1, t2, d2),
        "x0": x0,
        "baseline_mode": baseline_mode,
    }


def compare_solvers(
    time_s: np.ndarray,
    residual: np.ndarray,
    box_mass_kg: float,
    solvers: Sequence[str] = cfg.SOLVERS,
) -> list:
    """Run each solver; return list of summary dicts (for validation tables)."""
    import time as _time

    rows = []
    for s in solvers:
        t0 = _time.perf_counter()
        try:
            out = optimize_ricto(time_s, residual, box_mass_kg, solver=s)
            elapsed = _time.perf_counter() - t0
            rows.append(
                {
                    "solver": s,
                    "success": out["success"],
                    "cost": out["cost"],
                    "t1": out["t1"],
                    "d1": out["d1"],
                    "t2": out["t2"],
                    "d2": out["d2"],
                    "nfev": out["nfev"],
                    "elapsed_s": elapsed,
                    "B": out["B"],
                    "message": out.get("message", ""),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "solver": s,
                    "success": False,
                    "cost": np.nan,
                    "t1": np.nan,
                    "d1": np.nan,
                    "t2": np.nan,
                    "d2": np.nan,
                    "nfev": -1,
                    "elapsed_s": _time.perf_counter() - t0,
                    "B": np.nan,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
    return rows

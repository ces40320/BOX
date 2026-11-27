"""Approach A: optimize Chest_l / Chest_r ellipsoid parameters (subject-level).

Variables (left/right symmetric): radii×3, translation×3 (z mirrored),
rotation×3, optional quadrant. Objective = jump penalty + good-frame
length/MA RMSE + smoothness + parameter deviation.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from wrap_detect_lib import (
    CHEST_WRAP_NAMES,
    JUMP_DL_M,
    _apply_ik_row,
    import_opensim,
    list_chest_path_muscles,
)
from chest_diag_lib import (
    L5S1_COORDS,
    batch_moment_arms,
    chest_out_dir,
    get_chest_ellipsoid_params,
    length_jump_count,
    numerical_moment_arms,
    rmse,
    write_json,
)

# Relative bounds vs baseline.
RADII_FRAC = 0.30
TRANS_FRAC = 0.30
ROT_ABS_RAD = 0.30
ENDPOINT_CLEARANCE_M = 0.005

W_JUMP = 1e3
W_LENGTH = 1e2
W_MA = 50.0
W_SMOOTH = 10.0
W_PARAM = 1.0

QUADRANT_CHOICES = ("keep", "z", "-z", "all")


@dataclass
class EllipsoidParamVec:
    """Packed symmetric parameters relative to baseline right wrap."""

    radii_scale: np.ndarray  # (3,) multiplicative
    translation_delta: np.ndarray  # (3,) added to right; z mirrored on left
    rotation_delta: np.ndarray  # (3,)
    quadrant_mode: str = "keep"  # keep | z | -z | all

    def to_list(self) -> list[float]:
        q = {"keep": 0.0, "z": 1.0, "-z": 2.0, "all": 3.0}[self.quadrant_mode]
        return (
            self.radii_scale.tolist()
            + self.translation_delta.tolist()
            + self.rotation_delta.tolist()
            + [q]
        )

    @staticmethod
    def from_list(x: Sequence[float]) -> "EllipsoidParamVec":
        x = list(map(float, x))
        qi = int(round(x[9])) if len(x) > 9 else 0
        qi = max(0, min(3, qi))
        return EllipsoidParamVec(
            radii_scale=np.array(x[0:3], dtype=float),
            translation_delta=np.array(x[3:6], dtype=float),
            rotation_delta=np.array(x[6:9], dtype=float),
            quadrant_mode=QUADRANT_CHOICES[qi],
        )

    @staticmethod
    def identity() -> "EllipsoidParamVec":
        return EllipsoidParamVec(
            radii_scale=np.ones(3),
            translation_delta=np.zeros(3),
            rotation_delta=np.zeros(3),
            quadrant_mode="keep",
        )


def _set_vec3(obj_set, values: Sequence[float]) -> None:
    import opensim as osim
    obj_set(osim.Vec3(float(values[0]), float(values[1]), float(values[2])))


def apply_ellipsoid_params(
    osim,
    model,
    baseline: dict[str, dict[str, Any]],
    params: EllipsoidParamVec,
) -> None:
    """Mutate Chest_r / Chest_l on ``model`` from baseline + params."""
    for wn in CHEST_WRAP_NAMES:
        if wn not in baseline:
            continue
        base = baseline[wn]
        body = model.updBodySet().get(base["body"])
        wset = body.upd_WrapObjectSet()
        wrap = None
        for i in range(wset.getSize()):
            w = wset.get(i)
            if w.getName() == wn:
                wrap = osim.WrapEllipsoid.safeDownCast(w)
                break
        if wrap is None:
            continue
        br = np.asarray(base["dimensions"], dtype=float)
        bt = np.asarray(base["translation"], dtype=float)
        brot = np.asarray(base["xyz_body_rotation"], dtype=float)
        radii = br * params.radii_scale
        trans = bt + params.translation_delta.copy()
        if wn.endswith("_l"):
            # mirror z translation delta (and keep baseline z sign structure)
            trans = bt.copy()
            d = params.translation_delta.copy()
            d[2] = -d[2]
            trans = bt + d
            rot = brot + params.rotation_delta * np.array([1.0, -1.0, 1.0])
        else:
            rot = brot + params.rotation_delta
        wrap.set_dimensions(osim.Vec3(float(radii[0]), float(radii[1]), float(radii[2])))
        wrap.set_translation(osim.Vec3(float(trans[0]), float(trans[1]), float(trans[2])))
        wrap.set_xyz_body_rotation(osim.Vec3(float(rot[0]), float(rot[1]), float(rot[2])))
        if params.quadrant_mode != "keep":
            try:
                if params.quadrant_mode == "all":
                    wrap.set_quadrant("all")
                elif wn.endswith("_r"):
                    wrap.set_quadrant("z" if params.quadrant_mode == "z" else "-z")
                else:
                    # left: invert z choice for anatomical mirroring of "keep"
                    if params.quadrant_mode == "z":
                        wrap.set_quadrant("-z")
                    elif params.quadrant_mode == "-z":
                        wrap.set_quadrant("z")
                    else:
                        wrap.set_quadrant(params.quadrant_mode)
            except Exception:  # noqa: BLE001
                pass


def params_within_constraints(
    baseline: dict[str, dict[str, Any]],
    params: EllipsoidParamVec,
) -> bool:
    if np.any(params.radii_scale < 1.0 - RADII_FRAC) or np.any(
        params.radii_scale > 1.0 + RADII_FRAC
    ):
        return False
    # translation relative to mean radius
    br = np.asarray(baseline.get("Chest_r", {}).get("dimensions", [0.1, 0.1, 0.1]))
    scale = float(np.mean(br))
    if np.any(np.abs(params.translation_delta) > TRANS_FRAC * scale):
        return False
    if np.any(np.abs(params.rotation_delta) > ROT_ABS_RAD):
        return False
    return True


def _ik_in_degrees(meta: dict) -> bool:
    v = str(meta.get("inDegrees") or meta.get("in_degrees") or "").strip().lower()
    if v in ("yes", "true", "1"):
        return True
    if v in ("no", "false", "0"):
        return False
    return True


def sample_frame_indices(
    n: int,
    fail_mask: np.ndarray | None,
    *,
    max_fail: int = 40,
    max_ok: int = 40,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    rng = rng or np.random.default_rng(0)
    idx = np.arange(n)
    if fail_mask is None or fail_mask.size != n:
        return np.sort(rng.choice(idx, size=min(max_ok + max_fail, n), replace=False))
    fail_i = idx[fail_mask]
    ok_i = idx[~fail_mask]
    take_f = fail_i if len(fail_i) <= max_fail else rng.choice(fail_i, max_fail, replace=False)
    take_o = ok_i if len(ok_i) <= max_ok else rng.choice(ok_i, max_ok, replace=False)
    return np.sort(np.concatenate([take_f, take_o]))


def objective_on_samples(
    *,
    osim,
    baseline_model_path: str,
    candidate_model_path: str,
    ik_path: str,
    sample_idx: np.ndarray,
    ok_mask: np.ndarray,
    muscles: Sequence[str] | None = None,
) -> dict[str, float]:
    """Compute objective terms on sampled IK frames."""
    from optimization.ricto_io import read_opensim_storage

    m0 = osim.Model(baseline_model_path)
    s0 = m0.initSystem()
    m1 = osim.Model(candidate_model_path)
    s1 = m1.initSystem()
    names = list(muscles) if muscles else list_chest_path_muscles(m0)
    names = [n for n in names if m1.getMuscles().contains(n)]
    ik_df, meta = read_opensim_storage(ik_path)
    tcol = "time" if "time" in ik_df.columns else "Time"
    indeg = _ik_in_degrees(meta)
    times = ik_df[tcol].to_numpy(dtype=float)

    len0_all = {m: np.full(len(times), np.nan) for m in names}
    len1_all = {m: np.full(len(times), np.nan) for m in names}
    length_err = []
    ma_err = []

    for fi in sample_idx:
        row = ik_df.iloc[int(fi)]
        _apply_ik_row(osim, m0, s0, row, indeg)
        _apply_ik_row(osim, m1, s1, row, indeg)
        for m in names:
            mus0 = m0.getMuscles().get(m)
            mus1 = m1.getMuscles().get(m)
            try:
                l0 = float(mus0.getGeometryPath().getLength(s0))
                l1 = float(mus1.getGeometryPath().getLength(s1))
            except Exception:  # noqa: BLE001
                continue
            len0_all[m][fi] = l0
            len1_all[m][fi] = l1
            if ok_mask[fi]:
                length_err.append((l0 - l1) ** 2)
                a0 = numerical_moment_arms(osim, m0, s0, mus0)
                a1 = numerical_moment_arms(osim, m1, s1, mus1)
                for c in L5S1_COORDS:
                    if np.isfinite(a0.get(c, np.nan)) and np.isfinite(a1.get(c, np.nan)):
                        ma_err.append((a0[c] - a1[c]) ** 2)

    # jump count needs denser series — evaluate all frames for lengths only
    for fi, (_, row) in enumerate(ik_df.iterrows()):
        if fi in set(int(i) for i in sample_idx):
            continue
        # skip full scan here for speed; jumps estimated on sample densification
        # caller should run full detect after optimize
        pass

    n_jumps = 0
    smooth = 0.0
    for m in names:
        # fill missing by re-sim all frames for this muscle if needed — expensive.
        # Use sample series only for smoothness; jumps via full pass optional flag.
        series = len1_all[m]
        finite = np.isfinite(series)
        if finite.sum() >= 3:
            idx = np.where(finite)[0]
            vals = series[idx]
            if len(vals) >= 3:
                smooth = max(smooth, float(np.nanmean(np.abs(np.diff(vals, n=2)))))
            n_jumps += length_jump_count(vals, times[idx])

    return {
        "n_jumps": float(n_jumps),
        "length_mse": float(np.mean(length_err)) if length_err else 0.0,
        "ma_mse": float(np.mean(ma_err)) if ma_err else 0.0,
        "smooth": float(smooth),
    }


def full_jump_count(
    osim, model_path: str, ik_path: str, muscles: Sequence[str] | None = None,
) -> int:
    from wrap_detect_lib import detect_length_jumps
    islands, jumped = detect_length_jumps(
        osim, model_path, ik_path, muscles=muscles, dl_m=JUMP_DL_M,
    )
    return len(islands)


def write_candidate_osim(
    osim,
    baseline_model_path: str,
    out_path: str,
    params: EllipsoidParamVec,
) -> dict[str, Any]:
    model = osim.Model(baseline_model_path)
    model.initSystem()
    baseline = get_chest_ellipsoid_params(osim, model)
    apply_ellipsoid_params(osim, model, baseline, params)
    model.finalizeConnections()
    model.initSystem()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    model.printToXML(out_path)
    return {
        "baseline": baseline,
        "params": {
            "radii_scale": params.radii_scale.tolist(),
            "translation_delta": params.translation_delta.tolist(),
            "rotation_delta": params.rotation_delta.tolist(),
            "quadrant_mode": params.quadrant_mode,
        },
        "applied": get_chest_ellipsoid_params(osim, model),
    }


FRAME_STRIDE = 5  # frames used for the length term (jumps use all frames)
MA_STRIDE = 10  # default frames used for the moment-arm term (0 = disable MA term)


def _preload_chunk(
    osim,
    baseline_model_path: str,
    ik_paths: Sequence[str],
    frame_stride: int,
    ma_stride: int,
) -> tuple[dict[str, dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Load baseline model once and cache IK + baseline lengths/MAs for a chunk."""
    from optimization.ricto_io import read_opensim_storage

    base_model = osim.Model(baseline_model_path)
    s0 = base_model.initSystem()
    baseline0 = get_chest_ellipsoid_params(osim, base_model)
    names = list_chest_path_muscles(base_model)
    base_muscles = [(m, base_model.getMuscles().get(m)) for m in names]

    cached: list[dict[str, Any]] = []
    for ik in ik_paths:
        ik_df, meta = read_opensim_storage(ik)
        tcol = "time" if "time" in ik_df.columns else "Time"
        indeg = _ik_in_degrees(meta)
        times = ik_df[tcol].to_numpy(dtype=float)
        stride_idx = np.arange(0, len(times), frame_stride, dtype=int)
        l0_stride: dict[str, np.ndarray] = {
            m: np.full(len(stride_idx), np.nan, dtype=float) for m in names
        }
        for si, fi in enumerate(stride_idx):
            _apply_ik_row(osim, base_model, s0, ik_df.iloc[int(fi)], indeg)
            for m, mus0 in base_muscles:
                try:
                    l0_stride[m][si] = float(mus0.getGeometryPath().getLength(s0))
                except Exception:  # noqa: BLE001
                    continue

        if ma_stride > 0:
            ma_idx = np.arange(0, len(times), ma_stride, dtype=int)
            ma0_stride: dict[str, np.ndarray] | None = {
                m: np.full((len(ma_idx), len(L5S1_COORDS)), np.nan, dtype=float)
                for m in names
            }
            for mi, fi in enumerate(ma_idx):
                _apply_ik_row(osim, base_model, s0, ik_df.iloc[int(fi)], indeg)
                ma_now = batch_moment_arms(osim, base_model, s0, base_muscles)
                for m in names:
                    ma0_stride[m][mi] = ma_now[m]
            ma_len = len(ma_idx)
        else:
            ma0_stride = None
            ma_len = 0

        cached.append({
            "ik_df": ik_df,
            "times": times,
            "indeg": indeg,
            "stride_idx": stride_idx,
            "ma_len": ma_len,
            "l0_stride": l0_stride,
            "ma0_stride": ma0_stride,
        })
    return baseline0, names, cached


def _eval_chunk(
    osim,
    baseline_model_path: str,
    baseline0: dict[str, dict[str, Any]],
    names: Sequence[str],
    cached_jobs: Sequence[dict[str, Any]],
    params: EllipsoidParamVec,
    ma_stride: int,
) -> tuple[int, float, int, float, int]:
    """Evaluate one candidate on a cached chunk of IK trials."""
    m1 = osim.Model(baseline_model_path)
    m1.initSystem()
    apply_ellipsoid_params(osim, m1, baseline0, params)
    m1.finalizeConnections()
    s1 = m1.initSystem()
    cand_muscles = [
        (m, m1.getMuscles().get(m)) for m in names if m1.getMuscles().contains(m)
    ]

    jump_sum = 0
    length_sum = 0.0
    n_len = 0
    ma_sum = 0.0
    n_ma = 0
    for cj in cached_jobs:
        ik_df = cj["ik_df"]
        times = cj["times"]
        indeg = cj["indeg"]
        stride_idx = cj["stride_idx"]
        l0_stride = cj["l0_stride"]
        ma0_stride = cj["ma0_stride"]
        n_frames = len(times)
        len1_all = {m: np.full(n_frames, np.nan, dtype=float) for m, _ in cand_muscles}
        ma1_stride = (
            {
                m: np.full((cj["ma_len"], len(L5S1_COORDS)), np.nan, dtype=float)
                for m, _ in cand_muscles
            }
            if ma_stride > 0 and ma0_stride is not None
            else None
        )

        for fi in range(n_frames):
            _apply_ik_row(osim, m1, s1, ik_df.iloc[fi], indeg)
            for m, mus1 in cand_muscles:
                try:
                    len1_all[m][fi] = float(mus1.getGeometryPath().getLength(s1))
                except Exception:  # noqa: BLE001
                    continue
            if ma1_stride is not None and fi % ma_stride == 0:
                mi = fi // ma_stride
                ma_now = batch_moment_arms(osim, m1, s1, cand_muscles)
                for m, _ in cand_muscles:
                    ma1_stride[m][mi] = ma_now[m]

        for m, _ in cand_muscles:
            series = len1_all[m]
            jump_sum += length_jump_count(series, times, dl_m=JUMP_DL_M)
            l0_vals = l0_stride[m]
            l1_vals = series[stride_idx]
            valid = np.isfinite(l0_vals) & np.isfinite(l1_vals)
            if np.any(valid):
                diff = l0_vals[valid] - l1_vals[valid]
                length_sum += float(np.sum(diff * diff))
                n_len += int(np.sum(valid))

            if ma1_stride is not None and ma0_stride is not None:
                ma0 = ma0_stride[m]
                ma1 = ma1_stride[m]
                ma_valid = np.isfinite(ma0) & np.isfinite(ma1)
                if np.any(ma_valid):
                    mdiff = ma0[ma_valid] - ma1[ma_valid]
                    ma_sum += float(np.sum(mdiff * mdiff))
                    n_ma += int(np.sum(ma_valid))

    return jump_sum, length_sum, n_len, ma_sum, n_ma


def _chunk_worker_loop(
    baseline_model_path: str,
    ik_paths: list[str],
    frame_stride: int,
    ma_stride: int,
    in_q,
    out_q,
) -> None:
    """Persistent worker owning one fixed IK chunk (100% cache hit rate)."""
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    import _ts_paths  # noqa: F401

    osim = import_opensim()
    baseline0, names, cached = _preload_chunk(
        osim, baseline_model_path, ik_paths, frame_stride, ma_stride,
    )
    out_q.put(("ready", None))
    while True:
        msg = in_q.get()
        if msg is None:
            break
        params = EllipsoidParamVec.from_list(msg)
        res = _eval_chunk(
            osim, baseline_model_path, baseline0, names, cached, params, ma_stride,
        )
        out_q.put(("res", res))


def optimize_ellipsoid(
    *,
    namecode: str,
    baseline_model_path: str,
    ik_jobs: list[dict],
    maxiter: int = 40,
    maxfev: int = 30,
    grid_radii: Sequence[float] = (0.95, 1.0, 1.05, 1.10, 1.15),
    grid_post_m: Sequence[float] = (0.0, 0.005, 0.010, 0.015),
    refine: bool = True,
    tag: str = "",
    workers: int = 16,
    ma_stride: int = MA_STRIDE,
) -> dict[str, Any]:
    """Grid search + optional Nelder-Mead refine. Returns params + paths."""
    try:
        from scipy.optimize import minimize
    except ImportError:  # pragma: no cover
        minimize = None
        refine = False

    osim = import_opensim()
    out_dir = chest_out_dir(namecode, "A")
    history: list[dict] = []
    _base_model = osim.Model(baseline_model_path)
    _base_model.initSystem()
    _baseline0 = get_chest_ellipsoid_params(osim, _base_model)
    names = list_chest_path_muscles(_base_model)

    ik_paths = [job["ik_path"] for job in ik_jobs]
    n_workers = max(1, min(int(workers), len(ik_paths) or 1))
    print(
        f"[A] preload {len(ik_paths)} trials (workers={n_workers}, "
        f"len_stride={FRAME_STRIDE}, ma_stride={ma_stride})…",
        flush=True,
    )

    procs: list[Any] = []
    in_qs: list[Any] = []
    out_q: Any = None
    cached_jobs: list[dict[str, Any]] = []

    if n_workers > 1:
        ctx = mp.get_context("spawn")
        out_q = ctx.Queue()
        chunks: list[list[str]] = [[] for _ in range(n_workers)]
        for i, pth in enumerate(ik_paths):
            chunks[i % n_workers].append(pth)
        for ch in chunks:
            iq = ctx.Queue()
            proc = ctx.Process(
                target=_chunk_worker_loop,
                args=(baseline_model_path, ch, FRAME_STRIDE, ma_stride, iq, out_q),
            )
            proc.start()
            procs.append(proc)
            in_qs.append(iq)
        for _ in procs:
            tag_msg, _ = out_q.get()
            if tag_msg != "ready":
                raise RuntimeError("Worker failed to initialize")
    else:
        _, names, cached_jobs = _preload_chunk(
            osim, baseline_model_path, ik_paths, FRAME_STRIDE, ma_stride,
        )

    def score_params(params: EllipsoidParamVec) -> float:
        if not params_within_constraints(_baseline0, params):
            return 1e6

        if n_workers > 1:
            plist = params.to_list()
            for iq in in_qs:
                iq.put(plist)
            jump_sum = 0
            length_sum = 0.0
            n_len = 0
            ma_sum = 0.0
            n_ma = 0
            for _ in procs:
                _, (js, ls, nl, ms, nm) = out_q.get()
                jump_sum += js
                length_sum += ls
                n_len += nl
                ma_sum += ms
                n_ma += nm
        else:
            jump_sum, length_sum, n_len, ma_sum, n_ma = _eval_chunk(
                osim, baseline_model_path, _baseline0, names, cached_jobs, params, ma_stride,
            )

        length_mse = length_sum / max(n_len, 1)
        ma_mse = ma_sum / max(n_ma, 1) if ma_stride > 0 else 0.0
        param_pen = float(
            np.sum((params.radii_scale - 1.0) ** 2)
            + np.sum(params.translation_delta ** 2) / 0.01 ** 2
            + np.sum(params.rotation_delta ** 2) / ROT_ABS_RAD ** 2
        )
        cost = (
            W_JUMP * jump_sum
            + W_LENGTH * length_mse
            + (W_MA * ma_mse if ma_stride > 0 else 0.0)
            + W_PARAM * param_pen
        )
        history.append({
            "params": params.to_list(),
            "n_jumps": jump_sum,
            "length_mse": length_mse,
            "ma_mse": ma_mse,
            "cost": cost,
        })
        return cost

    try:
        # --- coarse grid on isotropic scale + posterior translation ---
        best = EllipsoidParamVec.identity()
        best_cost = float("inf")
        for sc in grid_radii:
            for post in grid_post_m:
                p = EllipsoidParamVec(
                    radii_scale=np.array([sc, sc, sc], dtype=float),
                    translation_delta=np.array([-post, 0.0, 0.0], dtype=float),  # -X posterior
                    rotation_delta=np.zeros(3),
                    quadrant_mode="keep",
                )
                c = score_params(p)
                print(f"[A-grid] scale={sc:.2f} post={post:.3f} cost={c:.4g}", flush=True)
                if c < best_cost:
                    best_cost = c
                    best = p

        if refine and minimize is not None:
            x0 = np.array(best.to_list()[:9], dtype=float)

            n_eval = [0]

            def fun(x):
                vec = EllipsoidParamVec(
                    radii_scale=np.asarray(x[0:3], dtype=float),
                    translation_delta=np.asarray(x[3:6], dtype=float),
                    rotation_delta=np.asarray(x[6:9], dtype=float),
                    quadrant_mode=best.quadrant_mode,
                )
                c = score_params(vec)
                n_eval[0] += 1
                h = history[-1] if history else {}
                print(
                    f"[A-NM] eval {n_eval[0]}/{maxfev} cost={c:.4g} "
                    f"jumps={h.get('n_jumps', '?')} x={np.round(x, 4).tolist()}",
                    flush=True,
                )
                return c

            # Jump count is integer-valued, so the cost is piecewise flat; use a
            # coarse initial simplex (5% radii, 5 mm, 0.05 rad) instead of scipy's
            # 0.00025 default step for zero-valued entries.
            steps = np.array([0.05] * 3 + [0.005] * 3 + [0.05] * 3)
            simplex = np.vstack([x0] + [x0 + np.eye(9)[i] * steps[i] for i in range(9)])
            print(f"[A] Nelder-Mead refine (max {maxfev} evaluations)…", flush=True)
            res = minimize(fun, x0, method="Nelder-Mead",
                           options={"maxiter": maxiter, "maxfev": maxfev,
                                    "initial_simplex": simplex,
                                    "xatol": 1e-3, "fatol": 1e-3})
            best = EllipsoidParamVec(
                radii_scale=np.asarray(res.x[0:3], dtype=float),
                translation_delta=np.asarray(res.x[3:6], dtype=float),
                rotation_delta=np.asarray(res.x[6:9], dtype=float),
                quadrant_mode=best.quadrant_mode,
            )
            best_cost = float(res.fun)
        elif refine and minimize is None:
            print("[A] scipy not installed — skipping Nelder-Mead refine", flush=True)
    finally:
        for iq in in_qs:
            try:
                iq.put(None)
            except Exception:  # noqa: BLE001
                pass
        for proc in procs:
            proc.join(timeout=10)
            if proc.is_alive():
                proc.terminate()

    from PATH_RULE import ResultPaths
    rp = ResultPaths(namecode)
    sub = rp.sub_label
    out_osim = os.path.join(rp.model_dir, f"{sub}_ChestFix{tag}.osim")
    info = write_candidate_osim(osim, baseline_model_path, out_osim, best)
    payload = {
        "namecode": namecode,
        "sub_label": sub,
        "out_osim": out_osim,
        "best_cost": best_cost,
        "best_params": info["params"],
        "applied_ellipsoid": info["applied"],
        "baseline_ellipsoid": info["baseline"],
        "history": history[-50:],
        "n_ik_jobs": len(ik_jobs),
        "objective_weights": {
            "W_JUMP": W_JUMP, "W_LENGTH": W_LENGTH,
            "W_MA": W_MA if ma_stride > 0 else 0.0, "W_PARAM": W_PARAM,
            "frame_stride": FRAME_STRIDE,
            "ma_stride": ma_stride,
            "workers": n_workers,
        },
    }
    json_path = os.path.join(out_dir, f"chest_params_{sub}{tag}.json")
    write_json(json_path, payload)
    return payload

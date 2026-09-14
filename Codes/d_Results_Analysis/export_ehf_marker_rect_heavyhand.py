# -*- coding: utf-8 -*-
"""Build rectangular HeavyHand EHF estimates from BK (+ optional marker events)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RUN_TOOLS = _CODES / "c_Run_Tools"
for _p in (str(_CODES), str(_RUN_TOOLS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from optimization.ricto_ehf import ehf_from_bk_pos  # noqa: E402
from optimization.ricto_io import read_opensim_storage  # noqa: E402
from optimization.run_ricto import box_mass_from_condition  # noqa: E402
import PATH_RULE as _path  # noqa: E402
import SUB_Info as _sub_info  # noqa: E402

from abc_marker_events import (  # noqa: E402
    BC_PAIR_X_THRESHOLD_LADDER_M,
    BC_PAIR_X_THRESHOLD_M,
    DEFAULT_MIN_PAIR_DURATION_S,
    DEFAULT_PAIR_THRESHOLD_M,
    SHELF_PAIR_THRESHOLD_LADDER_M,
    detect_abc_events_from_rigidbody,
    pairs_to_dataframe,
    read_rigidbody_marker15,
    rigidbody_track_quality,
    fill_rigidbody_gaps,
)
from analysis_utils import (  # noqa: E402
    list_segments,
    load_storage,
    measured_contact_window,
    parse_condition,
)

# Cache Motive event tables: (namecode, cond, ...) → DataFrame | None
_EVENTS_CACHE: Dict[tuple, Optional[pd.DataFrame]] = {}
# Unlabeled grip/deposit pairs: (namecode, cond, thr, min_dur, max_dur) → DataFrame
_PAIRS_CACHE: Dict[tuple, Optional[pd.DataFrame]] = {}
# Cache Motive→segment local time offset (s):
# (namecode, cond, seg, grip_g, deposit_g) → float | None
_OFFSET_CACHE: Dict[tuple, Optional[float]] = {}
# Cache segment time span for offset math: (namecode, cond, seg) → (T, t0_local)
_SEG_TIME_CACHE: Dict[tuple, Optional[Tuple[float, float]]] = {}
# Per-condition Motive tap origin for bpm schedule: (namecode, cond) → t_tap
_TAP_CACHE: Dict[tuple, Optional[float]] = {}
# seg → (grip_global, deposit_global) assignment cache: (namecode, cond) → dict
_ASSIGN_CACHE: Dict[tuple, Dict[str, Tuple[float, float]]] = {}

# Deposit search horizon as a fraction of one ABC bpm segment duration.
_MAX_PAIR_DURATION_FRAC = 0.55


def _rect_weight(time_s: np.ndarray, t_on: float, t_off: float) -> np.ndarray:
    t = np.asarray(time_s, dtype=float)
    w = np.zeros_like(t)
    w[(t >= t_on) & (t <= t_off)] = 1.0
    return w


def _find_rigidbody_csv(namecode: str, cond: str) -> Optional[Path]:
    rp = _path.ResultPaths(namecode)
    rigid_dir = Path(rp.rigid_dir)
    if not rigid_dir.is_dir():
        return None
    mass, tempo = parse_condition(cond)
    keys = (cond, f"{int(mass)}kg", f"{tempo}bpm", f"{int(mass)}_{tempo}")
    cands = sorted(rigid_dir.glob("*.csv"))
    for key in keys:
        for p in cands:
            if key.lower() in p.name.lower():
                return p
    return cands[0] if cands else None


def _max_pair_duration_s(namecode: str, cond: str) -> float:
    bpm_dur = _bpm_segment_duration_s(namecode, cond)
    if bpm_dur is None:
        return 3.0
    return float(_MAX_PAIR_DURATION_FRAC) * float(bpm_dur)


def _events_for_condition(
    namecode: str,
    cond: str,
    *,
    skip_first_n_cycles: int = 1,
) -> Optional[pd.DataFrame]:
    key = (
        namecode,
        cond,
        skip_first_n_cycles,
        DEFAULT_MIN_PAIR_DURATION_S,
        round(_max_pair_duration_s(namecode, cond), 4),
    )
    if key in _EVENTS_CACHE:
        return _EVENTS_CACHE[key]
    csv_path = _find_rigidbody_csv(namecode, cond)
    if csv_path is None:
        _EVENTS_CACHE[key] = None
        return None
    info = _sub_info.subjects[namecode]
    n_cycles = int(info["conditions"][cond]["cycles"])
    try:
        events, _rigid, _pairs = detect_abc_events_from_rigidbody(
            str(csv_path),
            skip_first_n_cycles=skip_first_n_cycles,
            n_cycles=n_cycles,
            pair_threshold_m=DEFAULT_PAIR_THRESHOLD_M,
            min_pair_duration_s=DEFAULT_MIN_PAIR_DURATION_S,
            max_pair_duration_s=_max_pair_duration_s(namecode, cond),
        )
    except Exception:
        _EVENTS_CACHE[key] = None
        return None
    _EVENTS_CACHE[key] = events
    return events


def _pairs_for_condition(
    namecode: str,
    cond: str,
    *,
    pair_threshold_m: Optional[float] = None,
    axis_index: int = 1,
    pair_axis_index: Optional[int] = None,
    peak_both_signs: bool = False,
    mode: str = "shelf",
) -> Optional[pd.DataFrame]:
    """All grip/deposit pairs (no ABC labels).

    ``mode='shelf'``: vertical peaks (``-Y``), ΔY threshold (AB/CA).
    ``mode='bc_x'``: same vertical peaks, but |ΔX| threshold (BC lateral).
    """
    if mode == "bc_x":
        axis_index = 1
        pair_axis_index = 0
        peak_both_signs = False
        if pair_threshold_m is None:
            pair_threshold_m = float(BC_PAIR_X_THRESHOLD_M)
    elif pair_threshold_m is None:
        pair_threshold_m = float(DEFAULT_PAIR_THRESHOLD_M)

    key = (
        namecode,
        cond,
        mode,
        float(pair_threshold_m),
        int(axis_index),
        None if pair_axis_index is None else int(pair_axis_index),
        bool(peak_both_signs),
        DEFAULT_MIN_PAIR_DURATION_S,
        round(_max_pair_duration_s(namecode, cond), 4),
    )
    if key in _PAIRS_CACHE:
        return _PAIRS_CACHE[key]
    csv_path = _find_rigidbody_csv(namecode, cond)
    if csv_path is None:
        _PAIRS_CACHE[key] = None
        return None
    try:
        _events, rigid, pairs = detect_abc_events_from_rigidbody(
            str(csv_path),
            skip_first_n_cycles=0,
            n_cycles=None,
            pair_threshold_m=float(pair_threshold_m),
            min_pair_duration_s=DEFAULT_MIN_PAIR_DURATION_S,
            max_pair_duration_s=_max_pair_duration_s(namecode, cond),
            axis_index=int(axis_index),
            pair_axis_index=pair_axis_index,
            peak_both_signs=bool(peak_both_signs),
        )
        df = pairs_to_dataframe(pairs, rigid["time"])
    except Exception:
        _PAIRS_CACHE[key] = None
        return None
    _PAIRS_CACHE[key] = df
    return df


def _adapt_pairs_to_target(
    namecode: str,
    cond: str,
    *,
    mode: str,
    target_n: int,
) -> Tuple[Optional[pd.DataFrame], Optional[float]]:
    """Lower pair threshold until ``target_n`` pairs (or ladder floor).

    Prints ``[MARKER-CRITICAL]`` when track is dead or still short after
    adaptation - never silently accept under-count.
    """
    ladder = (
        SHELF_PAIR_THRESHOLD_LADDER_M
        if mode == "shelf"
        else BC_PAIR_X_THRESHOLD_LADDER_M
    )
    csv_path = _find_rigidbody_csv(namecode, cond)
    if csv_path is None:
        print(
            f"[MARKER-CRITICAL] {namecode} {cond}: no Motive rigidbody CSV "
            f"(need >={target_n} {mode} pairs)"
        )
        return None, None

    try:
        rigid = read_rigidbody_marker15(str(csv_path))
        xyz = fill_rigidbody_gaps(rigid["box_xyz"], rigid["time"])
        ok, qmsg = rigidbody_track_quality(xyz)
    except Exception as e:
        print(
            f"[MARKER-CRITICAL] {namecode} {cond}: rigidbody unreadable ({e})"
        )
        return None, None
    if not ok:
        print(
            f"[MARKER-CRITICAL] {namecode} {cond}: Motive track unusable "
            f"({qmsg}) - cannot detect {mode} events "
            f"(need >={target_n} pairs)"
        )
        return None, None

    best: Optional[pd.DataFrame] = None
    best_thr: Optional[float] = None
    for thr in ladder:
        df = _pairs_for_condition(
            namecode, cond, mode=mode, pair_threshold_m=float(thr)
        )
        best, best_thr = df, float(thr)
        n = 0 if df is None else len(df)
        if n >= int(target_n):
            if float(thr) < float(ladder[0]) - 1e-12:
                print(
                    f"[MARKER-ADAPT] {namecode} {cond} {mode}: "
                    f"thr {ladder[0]}->{thr:g} m to reach "
                    f"{n}/{target_n} pairs"
                )
            return df, best_thr

    n_best = 0 if best is None else len(best)
    print(
        f"[MARKER-CRITICAL] {namecode} {cond} {mode}: still short after "
        f"thr ladder - got {n_best}/{target_n} pairs "
        f"(last thr={best_thr} m; track {qmsg})"
    )
    return best, best_thr


def _bpm_segment_duration_s(namecode: str, cond: str) -> Optional[float]:
    rp = _path.ResultPaths(namecode)
    seg_cfg = getattr(rp, "segmentation", None) or {}
    bpm_map = seg_cfg.get("BPM_DURATION") or {}
    _mass, tempo = parse_condition(cond)
    if tempo in bpm_map:
        return float(bpm_map[tempo])
    if str(tempo) in bpm_map:
        return float(bpm_map[str(tempo)])
    return None


def _seg_total_index(seg: str) -> Optional[int]:
    """0-based ABC index (1AB→0, 1BC→1, 1CA→2, 2AB→3, …)."""
    s = str(seg).strip().upper()
    for phase in ("AB", "BC", "CA"):
        if s.endswith(phase) and s[: -len(phase)].isdigit():
            cyc = int(s[: -len(phase)])
            phase_i = ("AB", "BC", "CA").index(phase)
            return (cyc - 1) * 3 + phase_i
    return None


def _estimate_motive_offset_s(
    namecode: str,
    cond: str,
    seg: str,
    grip_g: float,
    deposit_g: float,
) -> Optional[float]:
    """Map Motive global time → segment local: ``t_local = t_global - offset``.

    Prefer bpm_window reconstruction when marker contact falls inside the
    scheduled window; otherwise center the contact interval in ``[0, T]``.
    """
    key = (namecode, cond, seg, round(float(grip_g), 4), round(float(deposit_g), 4))
    if key in _OFFSET_CACHE:
        return _OFFSET_CACHE[key]

    seg_key = (namecode, cond, seg)
    if seg_key in _SEG_TIME_CACHE:
        span = _SEG_TIME_CACHE[seg_key]
        if span is None:
            _OFFSET_CACHE[key] = None
            return None
        T, t0_local = span
    else:
        rp = _path.ResultPaths(namecode)
        cp = rp.for_condition(cond)
        T = None
        t0_local = 0.0
        for path in (
            cp.bk_path(seg, "pos_global"),
            cp.extload_path(seg, "MeasuredEHF"),
        ):
            if os.path.isfile(path):
                try:
                    df, _ = read_opensim_storage(path)
                    t = df["time"].to_numpy(dtype=float)
                    if t.size >= 2:
                        T = float(t[-1] - t[0])
                        t0_local = float(t[0])
                        break
                except Exception:
                    continue
        else:
            _SEG_TIME_CACHE[seg_key] = None
            _OFFSET_CACHE[key] = None
            return None
        _SEG_TIME_CACHE[seg_key] = (float(T), float(t0_local))

    dur = _bpm_segment_duration_s(namecode, cond)
    if dur is None:
        dur = T + t0_local
    idx = _seg_total_index(seg)

    offset: Optional[float] = None
    if idx is not None and dur > 0 and deposit_g > grip_g:
        # ps <= grip and deposit <= ps+dur  →  deposit-dur <= ps <= grip
        ps_lo = float(deposit_g) - float(dur)
        ps_hi = float(grip_g)
        if ps_hi >= ps_lo:
            target_local_mid = 0.40 * float(dur)
            contact_mid = 0.5 * (float(grip_g) + float(deposit_g))
            ps_pref = contact_mid - target_local_mid
            ps = float(np.clip(ps_pref, ps_lo, ps_hi))
            offset = ps - t0_local

    if offset is None and deposit_g > grip_g and (T + t0_local) > 0:
        contact_mid = 0.5 * (float(grip_g) + float(deposit_g))
        local_mid = t0_local + 0.5 * T
        offset = contact_mid - local_mid

    _OFFSET_CACHE[key] = offset
    return offset


def _estimate_motive_t_tap(
    namecode: str,
    cond: str,
    pairs: Optional[pd.DataFrame] = None,
) -> Optional[float]:
    """Estimate trial ``t_tap`` so pair midpoints fall in bpm segment windows.

    Segment ``k`` occupies Motive global ``[t_tap+(1+k)*bpm, t_tap+(2+k)*bpm]``
    (same convention as ``run_get_exp_data``). Grid-searches ``t_tap`` to
    maximize how many clean pairs land in some segment window.
    """
    use_pairs = pairs
    if use_pairs is None:
        use_pairs = _pairs_for_condition(namecode, cond)
    n_pairs = 0 if use_pairs is None else len(use_pairs)
    key = (namecode, cond, n_pairs)
    if key in _TAP_CACHE:
        return _TAP_CACHE[key]

    bpm = _bpm_segment_duration_s(namecode, cond)
    if use_pairs is None or use_pairs.empty or bpm is None or bpm <= 0:
        _TAP_CACHE[key] = None
        return None

    mids = 0.5 * (
        use_pairs["grip_time"].to_numpy(dtype=float)
        + use_pairs["deposit_time"].to_numpy(dtype=float)
    )
    mids = mids[np.isfinite(mids)]
    if mids.size == 0:
        _TAP_CACHE[key] = None
        return None

    idxs = [
        i
        for i in (
            _seg_total_index(seg) for seg in list_segments(namecode, cond)
        )
        if i is not None
    ]
    if not idxs:
        _TAP_CACHE[key] = None
        return None
    i_max = int(max(idxs))

    t0 = float(np.min(mids) - 2.0 * float(bpm))
    t1 = float(np.min(mids) + float(bpm))
    grid = np.linspace(t0, t1, 81)
    best_tap = None
    best_hits = -1
    for tap in grid:
        hits = 0
        for mid in mids:
            for k in range(i_max + 1):
                ps = float(tap) + (1 + k) * float(bpm)
                pe = ps + float(bpm)
                if ps <= mid <= pe:
                    hits += 1
                    break
        if hits > best_hits:
            best_hits = hits
            best_tap = float(tap)

    if best_tap is None or best_hits <= 0:
        _TAP_CACHE[key] = None
        return None
    _TAP_CACHE[key] = best_tap
    return best_tap


def _assign_nearest_pairs_fallback(
    pairs: pd.DataFrame,
    windows: List[Tuple[str, float, float]],
    *,
    used_segs: set,
    phase_filter: Optional[object],
    max_mid_dist_s: float,
) -> Dict[str, Tuple[float, float]]:
    """Fill remaining windows with nearest unused pair (mid vs window center)."""
    assignment: Dict[str, Tuple[float, float]] = {}
    if pairs is None or pairs.empty or max_mid_dist_s <= 0:
        return assignment
    used_pair_idx: set = set()
    # Mark pairs already taken by comparing times against existing assignment values
    # is handled by caller passing only free pairs; track indices locally.
    for seg, ps, pe in windows:
        if seg in used_segs or not _phase_allowed(seg, phase_filter):
            continue
        center = 0.5 * (ps + pe)
        best_i = None
        best_dist = None
        best_gd = None
        for i, row in enumerate(pairs.itertuples(index=False)):
            if i in used_pair_idx:
                continue
            g_g = float(row.grip_time)
            d_g = float(row.deposit_time)
            if not (np.isfinite(g_g) and np.isfinite(d_g) and d_g > g_g):
                continue
            mid = 0.5 * (g_g + d_g)
            dist = abs(mid - center)
            if dist > float(max_mid_dist_s):
                continue
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_i = i
                best_gd = (g_g, d_g)
        if best_i is not None and best_gd is not None:
            assignment[seg] = best_gd
            used_segs.add(seg)
            used_pair_idx.add(best_i)
    return assignment


def _free_pairs_not_in_assignment(
    pairs: pd.DataFrame,
    assignment: Dict[str, Tuple[float, float]],
) -> pd.DataFrame:
    if pairs is None or pairs.empty:
        return pairs
    used = {(round(g, 3), round(d, 3)) for g, d in assignment.values()}
    mask = [
        (round(float(g), 3), round(float(d), 3)) not in used
        for g, d in zip(pairs["grip_time"], pairs["deposit_time"])
    ]
    return pairs.loc[mask].reset_index(drop=True)


def _phase_allowed(seg: str, phase_filter: Optional[object]) -> bool:
    if phase_filter is None:
        return True
    if isinstance(phase_filter, str):
        return str(seg).endswith(phase_filter)
    return any(str(seg).endswith(str(p)) for p in phase_filter)


def _assign_pairs_to_windows(
    pairs: pd.DataFrame,
    windows: List[Tuple[str, float, float]],
    *,
    used_segs: set,
    phase_filter: Optional[object] = None,
) -> Dict[str, Tuple[float, float]]:
    """One-to-one assignment by schedule-window overlap (not mid-in-window).

    For each free window (optionally phase-filtered), pick the unused pair with
    the largest time overlap, breaking ties by mid-point proximity to the
    window center. Shelf pairs must not be allowed into BC windows — callers
    pass ``phase_filter=('AB','CA')`` or ``'BC'``.
    """
    assignment: Dict[str, Tuple[float, float]] = {}
    if pairs is None or pairs.empty:
        return assignment

    used_pair_idx: set = set()
    for seg, ps, pe in windows:
        if seg in used_segs or not _phase_allowed(seg, phase_filter):
            continue
        best_i: Optional[int] = None
        best_key: Optional[Tuple[float, float]] = None
        best_gd: Optional[Tuple[float, float]] = None
        for i, row in enumerate(pairs.itertuples(index=False)):
            if i in used_pair_idx:
                continue
            g_g = float(row.grip_time)
            d_g = float(row.deposit_time)
            if not (np.isfinite(g_g) and np.isfinite(d_g) and d_g > g_g):
                continue
            ov = max(0.0, min(pe, d_g) - max(ps, g_g))
            if ov <= 0.0:
                continue
            mid = 0.5 * (g_g + d_g)
            key = (ov, -abs(mid - 0.5 * (ps + pe)))
            if best_key is None or key > best_key:
                best_key = key
                best_i = i
                best_gd = (g_g, d_g)
        if best_i is not None and best_gd is not None:
            assignment[seg] = best_gd
            used_segs.add(seg)
            used_pair_idx.add(best_i)
    return assignment


def _pair_assignment_for_condition(
    namecode: str, cond: str
) -> Dict[str, Tuple[float, float]]:
    """Map seg_label → (grip_global, deposit_global); each pair used at most once.

    Pass 1: shelf-height pairs (ΔY) → **AB and CA only** (never BC slots).
    Pass 2: lateral pairs (|ΔX|) → **BC only**.

    Pair thresholds are adapted downward until segment counts are met; remaining
    shortages are printed as ``[MARKER-CRITICAL]``.
    """
    cache_key = (namecode, cond)
    if cache_key in _ASSIGN_CACHE:
        return _ASSIGN_CACHE[cache_key]

    segs = list(list_segments(namecode, cond))
    n_ab = sum(s.endswith("AB") for s in segs)
    n_bc = sum(s.endswith("BC") for s in segs)
    n_ca = sum(s.endswith("CA") for s in segs)

    shelf_pairs, _shelf_thr = _adapt_pairs_to_target(
        namecode, cond, mode="shelf", target_n=n_ab + n_ca
    )
    bpm = _bpm_segment_duration_s(namecode, cond)
    t_tap = _estimate_motive_t_tap(namecode, cond, pairs=shelf_pairs)
    if shelf_pairs is None or shelf_pairs.empty or bpm is None or t_tap is None:
        if t_tap is None and shelf_pairs is not None and not shelf_pairs.empty:
            print(
                f"[MARKER-CRITICAL] {namecode} {cond}: cannot align Motive "
                f"schedule (t_tap) despite {len(shelf_pairs)} shelf pairs"
            )
        _ASSIGN_CACHE[cache_key] = {}
        return {}

    windows: List[Tuple[str, float, float]] = []
    for seg in segs:
        idx = _seg_total_index(seg)
        if idx is None:
            continue
        ps = float(t_tap) + (1 + int(idx)) * float(bpm)
        pe = ps + float(bpm)
        windows.append((seg, ps, pe))

    used_segs: set = set()
    assignment = _assign_pairs_to_windows(
        shelf_pairs.reset_index(drop=True),
        windows,
        used_segs=used_segs,
        phase_filter=("AB", "CA"),
    )
    # If overlap left holes but free shelf pairs remain, nearest-mid fallback.
    shelf_free = _free_pairs_not_in_assignment(shelf_pairs, assignment)
    if len(used_segs) < (n_ab + n_ca) and shelf_free is not None and not shelf_free.empty:
        assignment.update(
            _assign_nearest_pairs_fallback(
                shelf_free,
                windows,
                used_segs=used_segs,
                phase_filter=("AB", "CA"),
                max_mid_dist_s=2.5 * float(bpm),
            )
        )

    bc_pairs, _bc_thr = _adapt_pairs_to_target(
        namecode, cond, mode="bc_x", target_n=n_bc
    )
    if bc_pairs is not None and not bc_pairs.empty:
        bc_only = _free_pairs_not_in_assignment(bc_pairs, assignment)
        if bc_only is not None and not bc_only.empty:
            assignment.update(
                _assign_pairs_to_windows(
                    bc_only,
                    windows,
                    used_segs=used_segs,
                    phase_filter="BC",
                )
            )
            bc_free = _free_pairs_not_in_assignment(bc_pairs, assignment)
            n_bc_have = sum(s.endswith("BC") for s in used_segs)
            if n_bc_have < n_bc and bc_free is not None and not bc_free.empty:
                assignment.update(
                    _assign_nearest_pairs_fallback(
                        bc_free,
                        windows,
                        used_segs=used_segs,
                        phase_filter="BC",
                        max_mid_dist_s=2.5 * float(bpm),
                    )
                )

    a_ab = sum(s.endswith("AB") for s in assignment)
    a_bc = sum(s.endswith("BC") for s in assignment)
    a_ca = sum(s.endswith("CA") for s in assignment)
    if (a_ab, a_bc, a_ca) != (n_ab, n_bc, n_ca):
        print(
            f"[MARKER-CRITICAL] {namecode} {cond}: assignment incomplete "
            f"AB/BC/CA={a_ab}/{a_bc}/{a_ca} vs segs {n_ab}/{n_bc}/{n_ca} "
            f"(shelf_pairs={0 if shelf_pairs is None else len(shelf_pairs)}, "
            f"bc_pairs={0 if bc_pairs is None else len(bc_pairs)})"
        )

    _ASSIGN_CACHE[cache_key] = assignment
    return assignment


def marker_window_for_seg(
    namecode: str,
    cond: str,
    seg: str,
    *,
    skip_first_n_cycles: int = 1,
) -> Optional[Tuple[float, float]]:
    """Return segment-local ``(grip_time, deposit_time)`` or None.

    Clean Motive pairs are assigned one-to-one into bpm schedule windows by
    time overlap: shelf-height (ΔY) pairs → AB/CA only, then lateral (|ΔX|)
    pairs → BC. Unmatched phases → MeasuredEHF contact fallback.
    """
    del skip_first_n_cycles  # retained for call-site compatibility
    assignment = _pair_assignment_for_condition(namecode, cond)
    if seg not in assignment:
        return None
    g_g, d_g = assignment[seg]

    offset = _estimate_motive_offset_s(namecode, cond, seg, g_g, d_g)
    if offset is None:
        return None
    g = g_g - float(offset)
    d = d_g - float(offset)
    if not (np.isfinite(g) and np.isfinite(d) and d > g):
        return None
    return float(g), float(d)


def heavyhand_ehf_for_segment(
    namecode: str,
    cond: str,
    seg: str,
    *,
    use_markers: bool = True,
) -> Dict[str, np.ndarray]:
    rp = _path.ResultPaths(namecode)
    cp = rp.for_condition(cond)
    bk_path = cp.bk_path(seg, "pos_global")
    if not os.path.isfile(bk_path):
        raise FileNotFoundError(bk_path)
    pos_df, _ = read_opensim_storage(bk_path)
    mass = box_mass_from_condition(cond)
    ehf, _hands, _qc = ehf_from_bk_pos(pos_df, mass)
    t = np.asarray(ehf["time"], dtype=float)

    win = marker_window_for_seg(namecode, cond, seg) if use_markers else None
    if win is not None:
        t0, t1 = float(t[0]), float(t[-1])
        g, d = win
        if (g >= t0 - 0.5) and (d <= t1 + 0.5) and (d > g):
            w = _rect_weight(t, g, d)
        else:
            w = np.ones_like(t)
    else:
        w = np.ones_like(t)

    return {
        "time": t,
        "hand_force3_vx": w * ehf["fx_l"],
        "hand_force3_vy": w * ehf["fy_l"],
        "hand_force3_vz": w * ehf["fz_l"],
        "hand_force4_vx": w * ehf["fx_r"],
        "hand_force4_vy": w * ehf["fy_r"],
        "hand_force4_vz": w * ehf["fz_r"],
        "rect_w": w,
    }


def heavyhand_dataframe(namecode: str, cond: str, seg: str, **kwargs) -> pd.DataFrame:
    pack = heavyhand_ehf_for_segment(namecode, cond, seg, **kwargs)
    cols = [
        "time",
        "hand_force3_vx",
        "hand_force3_vy",
        "hand_force3_vz",
        "hand_force4_vx",
        "hand_force4_vy",
        "hand_force4_vz",
        "rect_w",
    ]
    return pd.DataFrame({c: pack[c] for c in cols})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--condition", default=None)
    ap.add_argument("--segments", default=None)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    rp = _path.ResultPaths(args.namecode)
    conds = [args.condition] if args.condition else list(rp.conditions.keys())
    out_root = Path(args.out_dir) if args.out_dir else (
        Path(_path.ANALYSIS_DIR) / "Asymmetric" / "EHF" / "HeavyHand" / "_export"
    )
    out_root.mkdir(parents=True, exist_ok=True)

    for cond in conds:
        segs = (
            [s.strip() for s in args.segments.split(",") if s.strip()]
            if args.segments
            else list_segments(args.namecode, cond)
        )
        for seg in segs:
            try:
                df = heavyhand_dataframe(args.namecode, cond, seg)
            except Exception as e:
                print(f"[skip] {cond} {seg}: {e}")
                continue
            path = out_root / f"{rp.sub_label}_{cond}_{seg}_HeavyHand_EHF.csv"
            df.to_csv(path, index=False)
            print("[ok]", path)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""EHF comparison → Analysis/Asymmetric/EHF/{app}/{axis}/SUB{n}_{hand}_{section}.csv

Alignment: MeasuredEHF 5 N window is the absolute clock. Each app is cropped to
that window; samples outside the app's own contact definition are zero-filled,
then time-resampled to 101 points before RMSE (full + quartiles).
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
for _p in (str(_CODES), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import (  # noqa: E402
    EHF_APPS,
    EHF_AXES,
    SECTIONS,
    align_force_to_gt_window,
    analysis_asymmetric_root,
    ehf_components_from_mot,
    ensure_domain_dirs,
    list_segments,
    load_storage,
    measured_contact_window,
    merge_metric_csv,
    resample_series_by_time,
    result_paths,
    ricto_contact_window,
    rmse_full_and_quartiles,
    row_dict,
    scale_ratio_row,
    section_of,
    write_section_timeseries,
)
from export_ehf_marker_rect_heavyhand import (  # noqa: E402
    heavyhand_dataframe,
    marker_window_for_seg,
)
from figure_outputs import (  # noqa: E402
    rebuild_suball_figures,
    write_subject_figures_from_rows,
)


def _load_app_mot(namecode: str, cond: str, seg: str, app: str):
    if app == "HeavyHand":
        return heavyhand_dataframe(namecode, cond, seg, use_markers=True)
    cp = result_paths(namecode).for_condition(cond)
    path = cp.extload_path(seg, app)
    return load_storage(path)


def _resolve_app_contact(
    namecode: str,
    cond: str,
    seg: str,
    app: str,
    gt_on: float,
    gt_off: float,
) -> Tuple[float, float, str, bool]:
    """Return (contact_on, contact_off, source, marker_ok_or_True)."""
    if app == "MeasuredEHF":
        return float(gt_on), float(gt_off), "gt_5n", True
    if app == "HeavyHand":
        win = marker_window_for_seg(namecode, cond, seg)
        if win is not None:
            return float(win[0]), float(win[1]), "marker", True
        return float(gt_on), float(gt_off), "gt_fallback", False
    # preRiCTO / postRiCTO
    win = ricto_contact_window(namecode, cond, seg)
    if win is not None:
        return float(win[0]), float(win[1]), "ricto", True
    return float(gt_on), float(gt_off), "gt_fallback", False


def process_subject(
    namecode: str,
    *,
    conditions: List[str] | None = None,
    plot: bool = False,
) -> dict:
    rp = result_paths(namecode)
    ensure_domain_dirs("EHF", EHF_APPS, EHF_AXES)
    root = analysis_asymmetric_root() / "EHF"
    conds = conditions or list(rp.conditions.keys())

    # rows[app][axis][hand][section] → list[dict]
    series_rows: Dict = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )
    scale_rows: List[dict] = []
    rmse_rows: List[dict] = []
    n_ok = n_skip = 0

    for cond in conds:
        for seg in list_segments(namecode, cond):
            section = section_of(seg)
            try:
                me_df = _load_app_mot(namecode, cond, seg, "MeasuredEHF")
                t_on, t_off = measured_contact_window(me_df)
            except Exception as e:
                print(f"[skip] {cond} {seg} contact: {e}")
                n_skip += 1
                continue

            app_packs = {}
            contact_meta: Dict[str, dict] = {}
            try:
                for app in EHF_APPS:
                    c_on, c_off, src, ok_flag = _resolve_app_contact(
                        namecode, cond, seg, app, t_on, t_off
                    )
                    contact_meta[app] = {
                        "contact_on": c_on,
                        "contact_off": c_off,
                        "contact_source": src,
                        "contact_ok": ok_flag,
                    }
                    raw = _load_app_mot(namecode, cond, seg, app)
                    packs = {}
                    for hand in ("L", "R"):
                        comp = ehf_components_from_mot(raw, hand)
                        aligned = align_force_to_gt_window(
                            comp["time"],
                            {k: comp[k] for k in EHF_AXES},
                            t_on,
                            t_off,
                            c_on,
                            c_off,
                        )
                        t_gt = aligned["time"]
                        packs[hand] = {
                            ax: resample_series_by_time(t_gt, aligned[ax])
                            for ax in EHF_AXES
                        }
                        packs[hand]["_n_raw"] = len(t_gt)
                        packs[hand]["_n_zero_prefix"] = int(
                            aligned["_n_zero_prefix"][0]
                        )
                        packs[hand]["_n_zero_suffix"] = int(
                            aligned["_n_zero_suffix"][0]
                        )
                    app_packs[app] = packs
            except Exception as e:
                print(f"[skip] {cond} {seg} load: {e}")
                n_skip += 1
                continue

            n_raw = app_packs["MeasuredEHF"]["L"]["_n_raw"]
            # One scale row per app for contact QC (MeasuredEHF first).
            for app in EHF_APPS:
                meta = contact_meta[app]
                scale_rows.append(
                    scale_ratio_row(
                        cond=cond,
                        seg=seg,
                        onset_t=t_on,
                        offset_t=t_off,
                        n_raw=n_raw,
                        contact_on=meta["contact_on"],
                        contact_off=meta["contact_off"],
                        n_zero_prefix=app_packs[app]["L"]["_n_zero_prefix"],
                        n_zero_suffix=app_packs[app]["L"]["_n_zero_suffix"],
                        contact_source=f"{app}:{meta['contact_source']}",
                    )
                )

            for app in EHF_APPS:
                for hand in ("L", "R"):
                    for ax in EHF_AXES:
                        series_rows[app][ax][hand][section].append(
                            row_dict(cond, seg, app_packs[app][hand][ax])
                        )

            for app in EHF_APPS:
                if app == "MeasuredEHF":
                    continue
                for hand in ("L", "R"):
                    for ax in EHF_AXES:
                        metrics = rmse_full_and_quartiles(
                            app_packs["MeasuredEHF"][hand][ax],
                            app_packs[app][hand][ax],
                        )
                        rmse_rows.append(
                            {
                                "cond": cond,
                                "section": section,
                                "seg": seg,
                                "hand": hand,
                                "axis": ax,
                                "app": app,
                                **metrics,
                            }
                        )
            n_ok += 1
            print(f"[ok] {cond} {seg}")

    for app in EHF_APPS:
        for ax in EHF_AXES:
            for hand in ("L", "R"):
                for section in SECTIONS:
                    path = root / app / ax / f"{rp.sub_label}_{hand}_{section}.csv"
                    write_section_timeseries(
                        path, series_rows[app][ax][hand][section], conds=conds
                    )

        mdir = root / app / "_metrics"
        rmse_app = [r for r in rmse_rows if r["app"] == app]
        if rmse_app:
            merge_metric_csv(
                mdir / f"RMSE_{rp.sub_label}.csv",
                rmse_app,
                conds=conds,
                sort_cols=["cond", "section", "seg", "hand", "axis"],
            )

    m_me = root / "MeasuredEHF" / "_metrics"
    if scale_rows:
        merge_metric_csv(
            m_me / f"resample_scale_{rp.sub_label}.csv",
            scale_rows,
            conds=conds,
            sort_cols=["cond", "section", "seg", "contact_source"],
        )
    if rmse_rows:
        merge_metric_csv(
            m_me / f"RMSE_all_apps_{rp.sub_label}.csv",
            rmse_rows,
            conds=conds,
            sort_cols=["cond", "section", "seg", "hand", "axis", "app"],
        )

    if plot:
        n_fig = write_subject_figures_from_rows(
            "EHF",
            rp.sub_label,
            series_rows=series_rows,
            apps=EHF_APPS,
            axes=EHF_AXES,
            sections=SECTIONS,
            hands=("L", "R"),
            title_prefix="EHF",
            ylabel_fn=lambda ax: f"{ax} force (N)",
        )
        suball = rebuild_suball_figures(
            "EHF",
            axes=EHF_AXES,
            hands=("L", "R"),
            title_prefix="EHF",
            ylabel_fn=lambda ax: f"{ax} force (N)",
        )
        print(f"[figures] EHF subject={n_fig}  SUBALL={suball}")

    return {"ok": n_ok, "skip": n_skip, "sub": rp.sub_label}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--conditions", default=None, help="Comma-separated")
    ap.add_argument("--plot", action="store_true")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()
    conds = (
        [c.strip() for c in args.conditions.split(",") if c.strip()]
        if args.conditions
        else None
    )
    do_plot = bool(args.plot) and not bool(args.no_plot)
    print(process_subject(args.namecode, conditions=conds, plot=do_plot))


if __name__ == "__main__":
    main()

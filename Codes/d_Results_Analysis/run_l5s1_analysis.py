# -*- coding: utf-8 -*-
"""L5S1 JRF/moment → Analysis/Asymmetric/L5S1/{app}/{axis}/SUB{n}_{section}.csv"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
for _p in (str(_CODES), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import (  # noqa: E402
    EHF_APPS,
    L5S1_FORCE_AXES,
    L5S1_FORCE_COLS,
    L5S1_MOMENT_AXES,
    L5S1_MOMENT_COLS,
    SECTIONS,
    analysis_asymmetric_root,
    crop_by_time,
    ensure_domain_dirs,
    figures_dir,
    list_segments,
    load_storage,
    mean_std_plot,
    measured_contact_window,
    merge_metric_csv,
    resample_series,
    result_paths,
    rmse_full_and_quartiles,
    row_dict,
    rows_to_matrix,
    scale_ratio_row,
    section_of,
    write_section_timeseries,
)

L5S1_AXES = L5S1_FORCE_AXES + L5S1_MOMENT_AXES


def _jr_components(df) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {"time": df["time"].to_numpy(dtype=float)}
    for ax, col in {**L5S1_FORCE_COLS, **L5S1_MOMENT_COLS}.items():
        if col not in df.columns:
            raise KeyError(f"missing JR column {col}")
        out[ax] = df[col].to_numpy(dtype=float)
    fx, fy, fz = out["Force_AP"], out["Force_Vertical"], out["Force_ML"]
    out["Force_Resultant"] = np.sqrt(fx**2 + fy**2 + fz**2)
    return out


def process_subject(
    namecode: str,
    *,
    conditions: List[str] | None = None,
    plot: bool = False,
) -> dict:
    rp = result_paths(namecode)
    ensure_domain_dirs("L5S1", EHF_APPS, L5S1_AXES)
    root = analysis_asymmetric_root() / "L5S1"
    conds = conditions or list(rp.conditions.keys())

    series_rows: Dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    scale_rows: List[dict] = []
    rmse_rows: List[dict] = []
    n_ok = n_skip = 0

    for cond in conds:
        cp = rp.for_condition(cond)
        for seg in list_segments(namecode, cond):
            section = section_of(seg)
            me_path = cp.extload_path(seg, "MeasuredEHF")
            try:
                me_df = load_storage(me_path)
                t_on, t_off = measured_contact_window(me_df)
            except Exception as e:
                print(f"[skip] {cond} {seg} contact: {e}")
                n_skip += 1
                continue

            app_packs = {}
            try:
                for app in EHF_APPS:
                    jr_path = cp.jr_path(seg, app)
                    if not os.path.isfile(jr_path):
                        raise FileNotFoundError(jr_path)
                    jr = _jr_components(load_storage(jr_path))
                    cropped = crop_by_time(
                        jr["time"],
                        {ax: jr[ax] for ax in L5S1_AXES},
                        t_on,
                        t_off,
                    )
                    app_packs[app] = {
                        ax: resample_series(cropped[ax]) for ax in L5S1_AXES
                    }
                    app_packs[app]["_n_raw"] = len(cropped["time"])
            except Exception as e:
                print(f"[skip] {cond} {seg} JR: {e}")
                n_skip += 1
                continue

            scale_rows.append(
                scale_ratio_row(
                    cond=cond,
                    seg=seg,
                    onset_t=t_on,
                    offset_t=t_off,
                    n_raw=app_packs["MeasuredEHF"]["_n_raw"],
                )
            )
            for app in EHF_APPS:
                for ax in L5S1_AXES:
                    series_rows[app][ax][section].append(
                        row_dict(cond, seg, app_packs[app][ax])
                    )
            for app in EHF_APPS:
                if app == "MeasuredEHF":
                    continue
                for ax in L5S1_AXES:
                    metrics = rmse_full_and_quartiles(
                        app_packs["MeasuredEHF"][ax], app_packs[app][ax]
                    )
                    rmse_rows.append(
                        {
                            "cond": cond,
                            "section": section,
                            "seg": seg,
                            "axis": ax,
                            "app": app,
                            **metrics,
                        }
                    )
            n_ok += 1
            print(f"[ok] {cond} {seg}")

    for app in EHF_APPS:
        for ax in L5S1_AXES:
            for section in SECTIONS:
                path = root / app / ax / f"{rp.sub_label}_{section}.csv"
                write_section_timeseries(
                    path, series_rows[app][ax][section], conds=conds
                )
        rmse_app = [r for r in rmse_rows if r["app"] == app]
        if rmse_app:
            merge_metric_csv(
                root / app / "_metrics" / f"RMSE_{rp.sub_label}.csv",
                rmse_app,
                conds=conds,
                sort_cols=["cond", "section", "seg", "axis"],
            )

    m_me = root / "MeasuredEHF" / "_metrics"
    if scale_rows:
        merge_metric_csv(
            m_me / f"resample_scale_{rp.sub_label}.csv",
            scale_rows,
            conds=conds,
            sort_cols=["cond", "section", "seg"],
        )
    if rmse_rows:
        merge_metric_csv(
            m_me / f"RMSE_all_apps_{rp.sub_label}.csv",
            rmse_rows,
            conds=conds,
            sort_cols=["cond", "section", "seg", "axis", "app"],
        )

    if plot:
        fig_root = figures_dir("L5S1")
        for ax in L5S1_AXES:
            for section in SECTIONS:
                by_app = {}
                for app in EHF_APPS:
                    rows = series_rows[app][ax][section]
                    if rows:
                        by_app[app] = rows_to_matrix(rows)
                if by_app:
                    unit = "N·m" if ax.startswith("Moment") else "N"
                    mean_std_plot(
                        by_app,
                        title=f"L5S1 {ax} {section} ({rp.sub_label})",
                        ylabel=f"{ax} ({unit})",
                        out_path=fig_root / f"{rp.sub_label}_{ax}_{section}.png",
                    )

    return {"ok": n_ok, "skip": n_skip, "sub": rp.sub_label}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--conditions", default=None)
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

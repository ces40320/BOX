# -*- coding: utf-8 -*-
"""Pelvis residual + Hicks → Analysis/Asymmetric/Residual/{app}/{Fx|Fy|Fz}/SUB{n}_{section}.csv"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
for _p in (str(_CODES), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import (  # noqa: E402
    EHF_APPS,
    RESIDUAL_AXES,
    RESIDUAL_COLS,
    SECTIONS,
    analysis_asymmetric_root,
    crop_by_time,
    ensure_domain_dirs,
    figures_dir,
    ground_and_hand_net_force,
    hicks_from_net,
    list_segments,
    load_storage,
    mean_std_plot,
    measured_contact_window,
    merge_metric_csv,
    resample_series,
    result_paths,
    row_dict,
    rows_to_matrix,
    scale_ratio_row,
    section_of,
    write_section_timeseries,
)


def _residual_pack(df) -> Dict[str, object]:
    out = {"time": df["time"].to_numpy(dtype=float)}
    for ax, col in RESIDUAL_COLS.items():
        if col not in df.columns:
            raise KeyError(f"missing residual column {col}")
        out[ax] = df[col].to_numpy(dtype=float)
    return out


def process_subject(
    namecode: str,
    *,
    conditions: List[str] | None = None,
    plot: bool = False,
) -> dict:
    rp = result_paths(namecode)
    ensure_domain_dirs("Residual", EHF_APPS, RESIDUAL_AXES)
    root = analysis_asymmetric_root() / "Residual"
    conds = conditions or list(rp.conditions.keys())

    series_rows: Dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    scale_rows: List[dict] = []
    hicks_rows: List[dict] = []
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

            try:
                net = ground_and_hand_net_force(me_df)
                h = hicks_from_net(net)
                hicks_rows.append(
                    {"cond": cond, "section": section, "seg": seg, **h}
                )

                for app in EHF_APPS:
                    so_path = cp.so_path(seg, app, "force")
                    if not os.path.isfile(so_path):
                        raise FileNotFoundError(so_path)
                    so = _residual_pack(load_storage(so_path))
                    cropped = crop_by_time(
                        so["time"],
                        {ax: so[ax] for ax in RESIDUAL_AXES},
                        t_on,
                        t_off,
                    )
                    for ax in RESIDUAL_AXES:
                        series_rows[app][ax][section].append(
                            row_dict(cond, seg, resample_series(cropped[ax]))
                        )
                    if app == "MeasuredEHF":
                        scale_rows.append(
                            scale_ratio_row(
                                cond=cond,
                                seg=seg,
                                onset_t=t_on,
                                offset_t=t_off,
                                n_raw=len(cropped["time"]),
                            )
                        )
            except Exception as e:
                print(f"[skip] {cond} {seg} residual: {e}")
                n_skip += 1
                continue

            n_ok += 1
            print(f"[ok] {cond} {seg}")

    for app in EHF_APPS:
        for ax in RESIDUAL_AXES:
            for section in SECTIONS:
                path = root / app / ax / f"{rp.sub_label}_{section}.csv"
                write_section_timeseries(
                    path, series_rows[app][ax][section], conds=conds
                )

    m_me = root / "MeasuredEHF" / "_metrics"
    if scale_rows:
        merge_metric_csv(
            m_me / f"resample_scale_{rp.sub_label}.csv",
            scale_rows,
            conds=conds,
            sort_cols=["cond", "section", "seg"],
        )
    if hicks_rows:
        hpath = m_me / f"Hicks_{rp.sub_label}.csv"
        hdf = pd.DataFrame(hicks_rows)
        if hpath.is_file():
            old = pd.read_csv(hpath)
            old = old[~old["cond"].isin(conds)]
            hdf = pd.concat([old, hdf], ignore_index=True)
        hdf = hdf.sort_values(["cond", "section", "seg"]).reset_index(drop=True)
        hdf.to_csv(hpath, index=False)
        summ = (
            hdf.groupby("cond", as_index=False)
            .agg(
                net_max_mean=("net_max", "mean"),
                net_max_std=("net_max", "std"),
                hicks_5pct_max_mean=("hicks_5pct_max", "mean"),
                hicks_5pct_rms_mean=("hicks_5pct_rms", "mean"),
                n_seg=("seg", "count"),
            )
        )
        summ.to_csv(m_me / f"Hicks_summary_{rp.sub_label}.csv", index=False)

    if plot:
        fig_root = figures_dir("Residual")
        for ax in RESIDUAL_AXES:
            for section in SECTIONS:
                by_app = {}
                for app in EHF_APPS:
                    rows = series_rows[app][ax][section]
                    if rows:
                        by_app[app] = rows_to_matrix(rows)
                if by_app:
                    mean_std_plot(
                        by_app,
                        title=f"Residual {ax} {section} ({rp.sub_label})",
                        ylabel=f"residual {ax} (N)",
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

# -*- coding: utf-8 -*-
"""Timing absolute error long table (RiCTO / marker vs MeasuredEHF 5 N GT)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import result_paths  # noqa: E402
from stats_io import (  # noqa: E402
    namecode_for_sub_label,
    ricto_summary_xlsx,
    stats_long_dir,
)
from stats_lmm import anthropometry_row  # noqa: E402


def _section_from_seg(seg: str) -> str:
    s = str(seg)
    for tag in ("AB", "BC", "CA"):
        if s.endswith(tag):
            return tag
    return s[-2:] if len(s) >= 2 else s


def build_timing_abserr(namecode: str) -> pd.DataFrame:
    rp = result_paths(namecode)
    xlsx = ricto_summary_xlsx(rp.sub_label)
    if not xlsx.is_file():
        raise FileNotFoundError(xlsx)
    bs = pd.read_excel(xlsx, sheet_name="by_segment")
    anthro = anthropometry_row(namecode)
    rows: list[dict] = []
    for _, r in bs.iterrows():
        base = {
            **anthro,
            "cond": r.get("condition"),
            "mass_kg": r.get("mass_kg"),
            "tempo_bpm": r.get("tempo_bpm"),
            "seg": r.get("seg"),
            "section": _section_from_seg(str(r.get("seg", ""))),
            "gt_onset": r.get("gt_onset"),
            "gt_offset": r.get("gt_offset"),
            "qc_warning": r.get("qc_warning"),
        }
        # RiCTO vs GT
        for event, err_col in (
            ("Grip", "err_onset_s"),
            ("Deposit", "err_offset_s"),
        ):
            err = r.get(err_col)
            if pd.isna(err):
                continue
            err_f = float(err)
            rows.append(
                {
                    **base,
                    "method": "RiCTO",
                    "event": event,
                    "err_s": err_f,
                    "abs_err_s": abs(err_f),
                }
            )
        # Box-marker vs GT (when present)
        marker_ok = r.get("marker_ok")
        ok = bool(marker_ok) if not (isinstance(marker_ok, float) and np.isnan(marker_ok)) else False
        if ok or (pd.notna(r.get("err_marker_onset_s")) or pd.notna(r.get("err_marker_offset_s"))):
            for event, err_col in (
                ("Grip", "err_marker_onset_s"),
                ("Deposit", "err_marker_offset_s"),
            ):
                err = r.get(err_col)
                if pd.isna(err):
                    continue
                err_f = float(err)
                rows.append(
                    {
                        **base,
                        "method": "BoxMarker",
                        "event": event,
                        "err_s": err_f,
                        "abs_err_s": abs(err_f),
                        "marker_ok": ok,
                    }
                )
    return pd.DataFrame(rows)


def process_subject(namecode: str) -> dict:
    df = build_timing_abserr(namecode)
    rp = result_paths(namecode)
    out = stats_long_dir() / f"timing_abserr_{rp.sub_label}.csv"
    df.to_csv(out, index=False)
    summary = (
        df.groupby(["method", "event"], as_index=False)
        .agg(
            n=("abs_err_s", "count"),
            abs_err_mean=("abs_err_s", "mean"),
            abs_err_std=("abs_err_s", "std"),
            err_bias=("err_s", "mean"),
        )
        .sort_values(["method", "event"])
    )
    sum_path = stats_long_dir() / f"timing_abserr_summary_{rp.sub_label}.csv"
    summary.to_csv(sum_path, index=False)
    return {"long": str(out), "summary": str(sum_path), "n": len(df)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--sub", default=None, help="e.g. SUB7 (optional)")
    args = ap.parse_args()
    nc = args.namecode
    if args.sub:
        found = namecode_for_sub_label(args.sub)
        if found:
            nc = found
    print(process_subject(nc))


if __name__ == "__main__":
    main()

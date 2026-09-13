# -*- coding: utf-8 -*-
"""RiCTO Summary workbook helpers (no Results/ CSV layer).

Output (flat):
  Analysis/<protocol>/RiCTO/Summary/SUB{n}_RiCTO_report.xlsx

Sheets: by_segment | by_condition | timing_error_summary

After each optimization segment, call ``upsert_optimize_row`` (or
``build_subject_report`` once at batch end). SO/JR are not required;
5 N timing columns come from ``_validation`` when available.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RUN_TOOLS = _CODES / "c_Run_Tools"
for _p in (str(_CODES), str(_HERE), str(_RUN_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import PATH_RULE as _path  # noqa: E402
from analysis_utils import list_segments, parse_condition, result_paths  # noqa: E402

TIMING_ERR_QC_S = 0.30

BY_SEGMENT_COLS = [
    "condition",
    "mass_kg",
    "tempo_bpm",
    "seg",
    "t1",
    "d1",
    "t2",
    "d2",
    "ricto_onset",
    "ricto_offset",
    "ricto_contact_dur_s",
    "gt_onset",
    "gt_offset",
    "gt_dur_s",
    "err_onset_s",
    "err_offset_s",
    "B",
    "solver",
    "success",
    "cost",
    "nfev",
    "residual_source",
    "qc_warning",
]

OPT_ROW_KEYS = (
    "seg",
    "residual_source",
    "solver",
    "success",
    "cost",
    "t1",
    "d1",
    "t2",
    "d2",
    "B",
    "nfev",
    "qc_warning",
)


def _ricto_root(protocol: str = "Asymmetric") -> Path:
    return Path(_path.ANALYSIS_DIR) / protocol / "RiCTO"


def _append_timing_qc(
    qc: object,
    err_onset: object,
    err_offset: object,
    *,
    thresh_s: float = TIMING_ERR_QC_S,
) -> str:
    parts: List[str] = []
    if isinstance(qc, str) and qc.strip() and qc.strip().lower() not in ("nan", "none"):
        parts.append(qc.strip())
    elif qc is not None and not (isinstance(qc, float) and np.isnan(qc)):
        s = str(qc).strip()
        if s and s.lower() not in ("nan", "none"):
            parts.append(s)
    try:
        eo = float(err_onset)
        ef = float(err_offset)
    except (TypeError, ValueError):
        return "; ".join(parts)
    flags = []
    if np.isfinite(eo) and abs(eo) > thresh_s:
        flags.append(f"|err_onset|={abs(eo):.3f}s>{thresh_s}s")
    if np.isfinite(ef) and abs(ef) > thresh_s:
        flags.append(f"|err_offset|={abs(ef):.3f}s>{thresh_s}s")
    if flags:
        parts.append("timing_qc: " + ", ".join(flags))
    return "; ".join(parts)


def _load_validation_timing(
    namecode: str, sub_label: str, protocol: str
) -> Optional[pd.DataFrame]:
    roots = [
        _ricto_root(protocol) / "_validation",
        Path(_path.ANALYSIS_DIR) / "RiCTO" / "_validation",
    ]
    for root in roots:
        for name in ("realdata_all_summary_fy5.csv", "realdata_all_summary.csv"):
            path = root / name
            if not path.is_file():
                continue
            vdf = pd.read_csv(path)
            mask = pd.Series(False, index=vdf.index)
            if "namecode" in vdf.columns:
                mask |= vdf["namecode"].astype(str) == namecode
            if "sub" in vdf.columns:
                mask |= vdf["sub"].astype(str) == sub_label
            hit = vdf.loc[mask].copy()
            if hit.empty:
                continue
            keep = [
                c
                for c in [
                    "condition",
                    "seg",
                    "gt_onset",
                    "gt_offset",
                    "gt_dur_s",
                    "err_onset_s",
                    "err_offset_s",
                    "n_gt_windows",
                    "fy_thresh_n",
                    "ok",
                ]
                if c in hit.columns
            ]
            return hit[keep]
    return None


def _read_existing_by_segment(xlsx: Path) -> pd.DataFrame:
    if not xlsx.is_file():
        return pd.DataFrame(columns=BY_SEGMENT_COLS)
    try:
        df = pd.read_excel(xlsx, sheet_name="by_segment")
    except Exception:
        return pd.DataFrame(columns=BY_SEGMENT_COLS)
    for c in BY_SEGMENT_COLS:
        if c not in df.columns:
            df[c] = np.nan
    return df[BY_SEGMENT_COLS].copy()


def _import_legacy_results_csvs(rp) -> pd.DataFrame:
    """One-shot import from deprecated Results/ or old Asymmetric tree."""
    rows = []
    results_dir = Path(rp.ricto_root()) / "Results"
    legacy_dirs = [
        results_dir,
        Path(_path.ANALYSIS_DIR) / "RiCTO" / rp.protocol / rp.sub_label,
    ]
    seen = set()
    for base in legacy_dirs:
        if not base.is_dir():
            continue
        for sum_csv in base.rglob("*_RiCTO_summary.csv"):
            if sum_csv in seen:
                continue
            seen.add(sum_csv)
            # Prefer flat Results name SUB7_7kg_10bpm_RiCTO_summary.csv
            name = sum_csv.name
            cond = None
            if name.startswith(rp.sub_label + "_") and name.endswith("_RiCTO_summary.csv"):
                mid = name[len(rp.sub_label) + 1 : -len("_RiCTO_summary.csv")]
                if mid in rp.conditions:
                    cond = mid
            if cond is None:
                # .../SUB7/7kg_10bpm/SUB7_7kg_10bpm_RiCTO_summary.csv
                parent = sum_csv.parent.name
                if parent in rp.conditions:
                    cond = parent
            if cond is None:
                continue
            df = pd.read_csv(sum_csv)
            mass, tempo = parse_condition(cond)
            valid = set(list_segments(rp.namecode, cond))
            for _, r in df.iterrows():
                seg = str(r.get("seg", ""))
                if seg and seg not in valid:
                    continue
                rows.append(
                    {
                        "condition": cond,
                        "mass_kg": mass,
                        "tempo_bpm": tempo,
                        "seg": seg,
                        "t1": r.get("t1"),
                        "d1": r.get("d1"),
                        "t2": r.get("t2"),
                        "d2": r.get("d2"),
                        "B": r.get("B"),
                        "solver": r.get("solver"),
                        "success": r.get("success"),
                        "cost": r.get("cost"),
                        "nfev": r.get("nfev"),
                        "residual_source": r.get("residual_source"),
                        "qc_warning": r.get("qc_warning", ""),
                    }
                )
    if not rows:
        return pd.DataFrame(columns=BY_SEGMENT_COLS)
    return pd.DataFrame(rows)


def _enrich_segment_df(
    df: pd.DataFrame,
    *,
    namecode: str,
    sub_label: str,
    protocol: str,
    timing_err_qc_s: float,
) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return pd.DataFrame(columns=BY_SEGMENT_COLS)

    if {"t1", "t2", "d2"}.issubset(out.columns):
        out["ricto_onset"] = out["t1"]
        out["ricto_offset"] = out["t2"] + out["d2"]
        out["ricto_contact_dur_s"] = out["ricto_offset"] - out["ricto_onset"]

    gt = _load_validation_timing(namecode, sub_label, protocol)
    # drop old gt cols before merge to refresh
    for c in (
        "gt_onset",
        "gt_offset",
        "gt_dur_s",
        "err_onset_s",
        "err_offset_s",
        "n_gt_windows",
        "fy_thresh_n",
        "ok",
    ):
        if c in out.columns:
            out = out.drop(columns=[c])
    if gt is not None and not gt.empty:
        out["seg"] = out["seg"].astype(str)
        gt = gt.copy()
        gt["seg"] = gt["seg"].astype(str)
        gt = gt.drop_duplicates(subset=["condition", "seg"], keep="first")
        out = out.merge(gt, on=["condition", "seg"], how="left")

    if "qc_warning" not in out.columns:
        out["qc_warning"] = ""
    # strip previous timing_qc tags then re-apply
    def _base_qc(q):
        if q is None or (isinstance(q, float) and np.isnan(q)):
            return ""
        s = str(q)
        parts = [p for p in s.split(";") if p.strip() and "timing_qc:" not in p]
        return "; ".join(p.strip() for p in parts if p.strip())

    out["qc_warning"] = [
        _append_timing_qc(
            _base_qc(q),
            eo,
            ef,
            thresh_s=timing_err_qc_s,
        )
        for q, eo, ef in zip(
            out["qc_warning"].tolist(),
            out["err_onset_s"].tolist()
            if "err_onset_s" in out.columns
            else [float("nan")] * len(out),
            out["err_offset_s"].tolist()
            if "err_offset_s" in out.columns
            else [float("nan")] * len(out),
        )
    ]

    for c in BY_SEGMENT_COLS:
        if c not in out.columns:
            out[c] = np.nan
    # de-dupe condition+seg keeping last
    out = out.sort_values(["condition", "seg"])
    out = out.drop_duplicates(subset=["condition", "seg"], keep="last")
    return out[BY_SEGMENT_COLS].reset_index(drop=True)


def _aggregates(sheet_all: pd.DataFrame, timing_err_qc_s: float):
    agg_rows = []
    for (condition, mass_kg, tempo_bpm), g in sheet_all.groupby(
        ["condition", "mass_kg", "tempo_bpm"], sort=False
    ):
        row = {
            "condition": condition,
            "mass_kg": mass_kg,
            "tempo_bpm": tempo_bpm,
            "n_seg": int(len(g)),
        }
        if "success" in g.columns:
            row["success_rate"] = float(pd.to_numeric(g["success"], errors="coerce").mean())
        for col, prefix in (
            ("cost", "cost"),
            ("ricto_contact_dur_s", "contact_dur"),
            ("B", "B"),
            ("err_onset_s", "err_onset"),
            ("err_offset_s", "err_offset"),
        ):
            if col in g.columns and g[col].notna().any():
                s = pd.to_numeric(g[col], errors="coerce")
                row[f"{prefix}_mean"] = float(s.mean())
                row[f"{prefix}_std"] = float(s.std(ddof=1)) if s.notna().sum() > 1 else 0.0
        if "err_onset_s" in g.columns:
            abs_on = pd.to_numeric(g["err_onset_s"], errors="coerce").abs()
            abs_off = pd.to_numeric(g["err_offset_s"], errors="coerce").abs()
            row["abs_err_onset_mean"] = float(abs_on.mean())
            row["abs_err_onset_std"] = float(abs_on.std(ddof=1)) if abs_on.notna().sum() > 1 else 0.0
            row["abs_err_offset_mean"] = float(abs_off.mean())
            row["abs_err_offset_std"] = float(abs_off.std(ddof=1)) if abs_off.notna().sum() > 1 else 0.0
            row["n_timing_qc_flag"] = int(
                ((abs_on > timing_err_qc_s) | (abs_off > timing_err_qc_s)).fillna(False).sum()
            )
        agg_rows.append(row)
    by_condition = pd.DataFrame(agg_rows)

    te_rows = []
    for condition, g in sheet_all.groupby("condition", sort=False):
        if "err_onset_s" not in g.columns or g["err_onset_s"].isna().all():
            continue
        abs_on = pd.to_numeric(g["err_onset_s"], errors="coerce").abs()
        abs_off = pd.to_numeric(g["err_offset_s"], errors="coerce").abs()
        te_rows.append(
            {
                "condition": condition,
                "n": int(len(g)),
                "abs_err_onset_mean": float(abs_on.mean()),
                "abs_err_onset_std": float(abs_on.std(ddof=1)) if abs_on.notna().sum() > 1 else 0.0,
                "abs_err_offset_mean": float(abs_off.mean()),
                "abs_err_offset_std": float(abs_off.std(ddof=1)) if abs_off.notna().sum() > 1 else 0.0,
                "timing_err_qc_s": timing_err_qc_s,
                "n_qc_flag": int(
                    ((abs_on > timing_err_qc_s) | (abs_off > timing_err_qc_s)).fillna(False).sum()
                ),
            }
        )
    return by_condition, pd.DataFrame(te_rows)


def _write_workbook(xlsx: Path, sheet_all: pd.DataFrame, timing_err_qc_s: float) -> Path:
    by_condition, timing_summary = _aggregates(sheet_all, timing_err_qc_s)
    xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        sheet_all.to_excel(writer, sheet_name="by_segment", index=False)
        by_condition.to_excel(writer, sheet_name="by_condition", index=False)
        if not timing_summary.empty:
            timing_summary.to_excel(
                writer, sheet_name="timing_error_summary", index=False
            )
    return xlsx


def _drop_error_log_rows(df: pd.DataFrame, namecode: str) -> pd.DataFrame:
    """Remove ``error_log`` segments; do not keep FALSE / placeholder rows for them."""
    if df is None or df.empty or "condition" not in df.columns or "seg" not in df.columns:
        return df
    rp = result_paths(namecode)
    keep = []
    for cond, g in df.groupby("condition", sort=False):
        cond_s = str(cond)
        if cond_s not in rp.conditions:
            keep.append(g)
            continue
        valid = set(list_segments(namecode, cond_s))
        keep.append(g[g["seg"].astype(str).isin(valid)])
    if not keep:
        return df.iloc[0:0].copy()
    return pd.concat(keep, ignore_index=True)


def upsert_optimize_row(
    namecode: str,
    condition: str,
    opt_row: Dict,
    *,
    timing_err_qc_s: float = TIMING_ERR_QC_S,
) -> Path:
    """Upsert one optimization segment into Summary xlsx and refresh sheets."""
    rp = result_paths(namecode)
    xlsx = Path(rp.ricto_report_path())
    seg = str(opt_row.get("seg", ""))
    # Never write rows for error_log segments (pipeline skips them; no ID/SO).
    if seg and seg not in set(list_segments(namecode, condition)):
        cur = _drop_error_log_rows(_read_existing_by_segment(xlsx), namecode)
        if not cur.empty:
            sheet = _enrich_segment_df(
                cur,
                namecode=namecode,
                sub_label=rp.sub_label,
                protocol=rp.protocol,
                timing_err_qc_s=timing_err_qc_s,
            )
            _write_workbook(xlsx, sheet, timing_err_qc_s)
        return xlsx

    mass, tempo = parse_condition(condition)
    new = {
        "condition": condition,
        "mass_kg": mass,
        "tempo_bpm": tempo,
        "seg": seg,
        "t1": opt_row.get("t1"),
        "d1": opt_row.get("d1"),
        "t2": opt_row.get("t2"),
        "d2": opt_row.get("d2"),
        "B": opt_row.get("B"),
        "solver": opt_row.get("solver"),
        "success": opt_row.get("success"),
        "cost": opt_row.get("cost"),
        "nfev": opt_row.get("nfev"),
        "residual_source": opt_row.get("residual_source"),
        "qc_warning": opt_row.get("qc_warning", ""),
    }
    cur = _read_existing_by_segment(xlsx)
    if cur.empty:
        # migrate legacy Results once if present
        cur = _import_legacy_results_csvs(rp)
    cur = pd.concat([cur, pd.DataFrame([new])], ignore_index=True)
    cur = _drop_error_log_rows(cur, namecode)
    sheet = _enrich_segment_df(
        cur,
        namecode=namecode,
        sub_label=rp.sub_label,
        protocol=rp.protocol,
        timing_err_qc_s=timing_err_qc_s,
    )
    _write_workbook(xlsx, sheet, timing_err_qc_s)
    return xlsx


def build_subject_report(
    namecode: str,
    *,
    timing_err_qc_s: float = TIMING_ERR_QC_S,
) -> Path:
    """Rebuild Summary xlsx from existing by_segment (+ optional legacy Results import)."""
    rp = result_paths(namecode)
    xlsx = Path(rp.ricto_report_path())
    cur = _read_existing_by_segment(xlsx)
    legacy = _import_legacy_results_csvs(rp)
    if not legacy.empty:
        cur = pd.concat([cur, legacy], ignore_index=True)
    if cur.empty:
        raise FileNotFoundError(
            f"No RiCTO summary rows for {namecode} (run optimization first)"
        )
    cur = _drop_error_log_rows(cur, namecode)
    if cur.empty:
        raise FileNotFoundError(
            f"No RiCTO summary rows for {namecode} after dropping error_log"
        )

    sheet = _enrich_segment_df(
        cur,
        namecode=namecode,
        sub_label=rp.sub_label,
        protocol=rp.protocol,
        timing_err_qc_s=timing_err_qc_s,
    )
    _write_workbook(xlsx, sheet, timing_err_qc_s)
    print("[ok]", xlsx)
    print(f"[qc] timing |err| threshold = {timing_err_qc_s} s")
    return xlsx


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--timing-err-qc", type=float, default=TIMING_ERR_QC_S)
    args = ap.parse_args()
    build_subject_report(args.namecode, timing_err_qc_s=args.timing_err_qc)


if __name__ == "__main__":
    main()

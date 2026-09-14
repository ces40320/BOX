# -*- coding: utf-8 -*-
"""L5S1 peak extraction + one-way repeated-measures ANOVA (within=app)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis_utils import (  # noqa: E402
    EHF_APPS,
    P_COLS,
    SECTIONS,
    analysis_asymmetric_root,
    parse_condition,
    result_paths,
)
from stats_io import stats_long_dir, stats_models_dir  # noqa: E402
from stats_lmm import anthropometry_row  # noqa: E402

L5S1_PEAK_AXIS = "Force_Resultant"
APPS_ANOVA = ("MeasuredEHF", "HeavyHand", "preRiCTO", "postRiCTO")


def _load_section_csv(app: str, axis: str, sub_label: str, section: str) -> pd.DataFrame:
    path = analysis_asymmetric_root() / "L5S1" / app / axis / f"{sub_label}_{section}.csv"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def peak_from_row(row: pd.Series) -> dict:
    y = np.array([row[c] for c in P_COLS], dtype=float)
    n = len(y)
    mid = n // 2
    i0 = int(np.nanargmax(y[:mid])) if np.any(np.isfinite(y[:mid])) else -1
    i1 = int(np.nanargmax(y[mid:])) + mid if np.any(np.isfinite(y[mid:])) else -1
    pct = np.linspace(0.0, 100.0, n)
    return {
        "initial_peak_mag": float(y[i0]) if i0 >= 0 else float("nan"),
        "initial_peak_time_pct": float(pct[i0]) if i0 >= 0 else float("nan"),
        "final_peak_mag": float(y[i1]) if i1 >= 0 else float("nan"),
        "final_peak_time_pct": float(pct[i1]) if i1 >= 0 else float("nan"),
    }


def build_l5s1_peaks(namecode: str, *, axis: str = L5S1_PEAK_AXIS) -> pd.DataFrame:
    rp = result_paths(namecode)
    anthro = anthropometry_row(namecode)
    rows: List[dict] = []
    for app in APPS_ANOVA:
        for section in SECTIONS:
            df = _load_section_csv(app, axis, rp.sub_label, section)
            if df.empty:
                continue
            for _, r in df.iterrows():
                mass, tempo = parse_condition(str(r["cond"]))
                peaks = peak_from_row(r)
                rows.append(
                    {
                        **anthro,
                        "cond": r["cond"],
                        "mass_kg": mass,
                        "tempo_bpm": tempo,
                        "seg": r["seg"],
                        "section": section,
                        "app": app,
                        "axis": axis,
                        **peaks,
                    }
                )
    return pd.DataFrame(rows)


def _wide_for_rm(peaks: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """One row per (cond,seg); columns = apps."""
    key = ["cond", "seg"]
    piv = peaks.pivot_table(index=key, columns="app", values=outcome, aggfunc="mean")
    piv = piv.reindex(columns=[a for a in APPS_ANOVA if a in piv.columns])
    return piv.dropna(how="any")


def run_rm_anova(peaks: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """Return (anova_table, posthoc_table, narrative_text)."""
    try:
        import pingouin as pg
    except ImportError:
        msg = "pingouin not installed; skip rmANOVA"
        return pd.DataFrame(), pd.DataFrame(), msg

    narratives: List[str] = []
    anova_rows: List[dict] = []
    post_rows: List[dict] = []
    outcomes = [
        ("initial_peak_mag", "Initial peak mag."),
        ("final_peak_mag", "Final peak mag."),
        ("initial_peak_time_pct", "Initial peak time"),
        ("final_peak_time_pct", "Final peak time"),
    ]
    for col, label in outcomes:
        long = peaks[["cond", "seg", "app", col]].dropna().rename(columns={col: "value"})
        if long["app"].nunique() < 2 or len(long) < 6:
            narratives.append(f"{label}\ninsufficient data\n")
            continue
        # subject unit = cond+seg (within-app repeated measures across apps)
        long = long.copy()
        long["unit"] = long["cond"].astype(str) + "|" + long["seg"].astype(str)
        try:
            aov = pg.rm_anova(
                data=long,
                dv="value",
                within="app",
                subject="unit",
                detailed=True,
                correction=True,
            )
        except Exception as e:
            narratives.append(f"{label}\nrmANOVA failed: {e}\n")
            continue
        # extract app effect row
        app_row = aov[aov["Source"].astype(str).str.lower().eq("app")]
        if app_row.empty:
            app_row = aov[aov["Source"].astype(str).str.contains("app", case=False, na=False)]
        if app_row.empty:
            app_row = aov.iloc[[0]]
        r0 = app_row.iloc[0]
        err_row = aov[aov["Source"].astype(str).str.lower().isin(("error", "residual"))]
        ddof1 = float(r0["DF"]) if "DF" in r0.index and pd.notna(r0["DF"]) else float("nan")
        ddof2 = (
            float(err_row.iloc[0]["DF"])
            if not err_row.empty and pd.notna(err_row.iloc[0]["DF"])
            else float("nan")
        )
        # GG-corrected dfs when sphericity violated
        eps = float(r0["eps"]) if "eps" in r0.index and pd.notna(r0.get("eps")) else 1.0
        if "p-GG-corr" in r0.index and pd.notna(r0.get("p-GG-corr")):
            p = float(r0["p-GG-corr"])
            p_note = "GG"
            if np.isfinite(ddof1) and np.isfinite(ddof2) and np.isfinite(eps):
                ddof1 = ddof1 * eps
                ddof2 = ddof2 * eps
        else:
            p = float(r0.get("p-unc", float("nan")))
            p_note = "unc"
        F = float(r0.get("F", float("nan")))
        sig = "significant" if (np.isfinite(p) and p < 0.05) else "non-significant"
        narratives.append(
            f"{label}\nF({ddof1:.2f}, {ddof2:.2f}) = {F:.3g}, p = {p:.3g}\t\t{sig} ({p_note})\n"
        )
        anova_rows.append(
            {
                "outcome": col,
                "label": label,
                "ddof1": ddof1,
                "ddof2": ddof2,
                "F": F,
                "p": p,
                "p_correction": p_note,
                "eps": eps,
                "significant": sig,
            }
        )
        try:
            ph = pg.pairwise_tests(
                data=long,
                dv="value",
                within="app",
                subject="unit",
                padjust="bonf",
            )
            for _, pr in ph.iterrows():
                post_rows.append(
                    {
                        "outcome": col,
                        "A": pr.get("A"),
                        "B": pr.get("B"),
                        "mean_diff": pr.get("mean(A)") - pr.get("mean(B)")
                        if pd.notna(pr.get("mean(A)")) and pd.notna(pr.get("mean(B)"))
                        else pr.get("diff", float("nan")),
                        "p_corr": pr.get("p-corr", pr.get("p-unc")),
                        "p_adjust": "bonf",
                    }
                )
        except Exception:
            pass

    text = "L5S1 One-way rm ANOVA Reports\n\n" + "\n".join(narratives)
    return pd.DataFrame(anova_rows), pd.DataFrame(post_rows), text


def process_subject(namecode: str) -> dict:
    rp = result_paths(namecode)
    peaks = build_l5s1_peaks(namecode)
    peak_path = stats_long_dir() / f"L5S1_peaks_{rp.sub_label}.csv"
    peaks.to_csv(peak_path, index=False)
    anova, post, text = run_rm_anova(peaks)
    model_dir = stats_models_dir()
    anova_path = model_dir / f"rmANOVA_L5S1_peaks_{rp.sub_label}.csv"
    post_path = model_dir / f"rmANOVA_L5S1_posthoc_{rp.sub_label}.csv"
    txt_path = model_dir / f"rmANOVA_L5S1_report_{rp.sub_label}.txt"
    if not anova.empty:
        anova.to_csv(anova_path, index=False)
    if not post.empty:
        post.to_csv(post_path, index=False)
    txt_path.write_text(text, encoding="utf-8")
    return {
        "peaks": str(peak_path),
        "anova": str(anova_path) if not anova.empty else "",
        "posthoc": str(post_path) if not post.empty else "",
        "report_txt": str(txt_path),
        "n_peaks": len(peaks),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    args = ap.parse_args()
    print(process_subject(args.namecode))


if __name__ == "__main__":
    main()

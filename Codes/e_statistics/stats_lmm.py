# -*- coding: utf-8 -*-
"""Linear mixed model toolkit for BOX Asymmetric analyses.

Tracks A/B (see implementation/ and research/). Track C deferred.
Outputs under Analysis/Asymmetric/_stats/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import SUB_Info as _sub_info  # noqa: E402
from analysis_utils import analysis_asymmetric_root, parse_condition, result_paths  # noqa: E402


def _stats_dir() -> Path:
    d = analysis_asymmetric_root() / "_stats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def anthropometry_row(namecode: str) -> dict:
    info = _sub_info.subjects[namecode]
    return {
        "namecode": namecode,
        "sub": f"SUB{info['SUB_number']}",
        "height_mm": info.get("height"),
        "body_mass_kg": info.get("body_mass"),
        "sex": info.get("sex"),
        "age": info.get("age"),
    }


def load_ehf_rmse(sub_label: str) -> pd.DataFrame:
    path = (
        analysis_asymmetric_root()
        / "EHF"
        / "MeasuredEHF"
        / "_metrics"
        / f"RMSE_all_apps_{sub_label}.csv"
    )
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def build_long_ehf_rmse(namecode: str) -> pd.DataFrame:
    rp = result_paths(namecode)
    df = load_ehf_rmse(rp.sub_label)
    anthro = anthropometry_row(namecode)
    rows = []
    for _, r in df.iterrows():
        mass, tempo = parse_condition(str(r["cond"]))
        rows.append(
            {
                **anthro,
                "cond": r["cond"],
                "mass_kg": mass,
                "tempo_bpm": tempo,
                "seg": r["seg"],
                "section": r.get("section", str(r["seg"])[-2:]),
                "hand": r["hand"],
                "axis": r["axis"],
                "app": r["app"],
                "RMSE_full": r["RMSE_full"],
                "RMSE_q1": r.get("RMSE_q1"),
                "RMSE_q2": r.get("RMSE_q2"),
                "RMSE_q3": r.get("RMSE_q3"),
                "RMSE_q4": r.get("RMSE_q4"),
            }
        )
    return pd.DataFrame(rows)


def descriptives_sub7(long_df: pd.DataFrame) -> pd.DataFrame:
    return (
        long_df.groupby(["app", "axis", "hand", "mass_kg", "tempo_bpm"], as_index=False)
        .agg(
            n=("RMSE_full", "count"),
            RMSE_mean=("RMSE_full", "mean"),
            RMSE_std=("RMSE_full", "std"),
            RMSE_median=("RMSE_full", "median"),
        )
        .sort_values(["app", "axis", "hand", "mass_kg", "tempo_bpm"])
    )


def try_fixed_ols(long_df: pd.DataFrame) -> str:
    try:
        import statsmodels.formula.api as smf
    except ImportError:
        return "statsmodels not installed; skip OLS"

    sub = long_df[long_df["axis"] == "Resultant"].copy()
    if sub.empty:
        return "no Resultant rows"
    model = smf.ols(
        "RMSE_full ~ C(app) * C(tempo_bpm) * C(mass_kg) + C(hand)",
        data=sub,
    ).fit()
    out = _stats_dir() / f"{sub['sub'].iloc[0]}_OLS_Resultant_RMSE.txt"
    out.write_text(model.summary().as_text(), encoding="utf-8")
    return str(out)


def lmm_skeleton_doc(long_df: pd.DataFrame) -> str:
    path = _stats_dir() / "lmm_skeleton_formulas.txt"
    text = """# Proposed LMM formulas (multi-subject; do not fit on n_subject=1)

# Python (statsmodels):
# mixed = smf.mixedlm(
#     "RMSE_full ~ C(app) * C(tempo_bpm) * C(mass_kg) + height_mm + body_mass_kg",
#     data=df,
#     groups=df["sub"],
#     re_formula="~1",
# )

# R (lme4):
# lmer(RMSE_full ~ app * tempo_bpm * mass_kg + height_mm + body_mass_kg
#      + (1 | sub), data=df)

n_rows_template = %d
n_subjects_in_template = %d
""" % (
        len(long_df),
        long_df["sub"].nunique(),
    )
    path.write_text(text, encoding="utf-8")
    return str(path)


def process_subject(namecode: str) -> dict:
    long_df = build_long_ehf_rmse(namecode)
    out = _stats_dir()
    rp = result_paths(namecode)
    long_path = out / f"lmm_long_template_EHF_RMSE_{rp.sub_label}.csv"
    long_df.to_csv(long_path, index=False)
    desc = descriptives_sub7(long_df)
    desc_path = out / f"{rp.sub_label}_rmse_by_factor.csv"
    desc.to_csv(desc_path, index=False)
    ols_path = try_fixed_ols(long_df)
    skel = lmm_skeleton_doc(long_df)
    return {
        "long": str(long_path),
        "descriptives": str(desc_path),
        "ols": ols_path,
        "skeleton": skel,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    args = ap.parse_args()
    print(process_subject(args.namecode))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Linear mixed model toolkit for BOX Asymmetric analyses.

Tracks A/B (see implementation/ and research/).
Outputs under Analysis/Asymmetric/_stats/ (long/ + models/).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_CODES = _HERE.parent
_RESULTS = _CODES / "d_Results_Analysis"
for _p in (str(_CODES), str(_RESULTS), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import SUB_Info as _sub_info  # noqa: E402
from analysis_utils import analysis_asymmetric_root, parse_condition, result_paths  # noqa: E402
from stats_io import stats_long_dir, stats_models_dir, stats_root, suball_namecodes  # noqa: E402


def _stats_dir() -> Path:
    return stats_root()


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
    body = anthro.get("body_mass_kg")
    rows = []
    for _, r in df.iterrows():
        mass, tempo = parse_condition(str(r["cond"]))
        mass_norm = (
            float(mass) / float(body)
            if body is not None and float(body) > 0 and np.isfinite(mass)
            else float("nan")
        )
        rows.append(
            {
                **anthro,
                "cond": r["cond"],
                "mass_kg": mass,
                "tempo_bpm": tempo,
                "mass_norm": mass_norm,
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
    # drop MeasuredEHF self-RMSE if present (usually compare apps only)
    sub = sub[sub["app"].astype(str) != "MeasuredEHF"]
    if sub.empty:
        sub = long_df[long_df["axis"] == "Resultant"].copy()
    model = smf.ols(
        "RMSE_full ~ C(app) * C(tempo_bpm) * C(mass_kg) + C(hand)",
        data=sub,
    ).fit()
    out = stats_models_dir() / f"{sub['sub'].iloc[0]}_OLS_Resultant_RMSE.txt"
    out.write_text(model.summary().as_text(), encoding="utf-8")
    # keep legacy flat copy for compatibility
    legacy = _stats_dir() / f"{sub['sub'].iloc[0]}_OLS_Resultant_RMSE.txt"
    legacy.write_text(model.summary().as_text(), encoding="utf-8")
    return str(out)


def lmm_skeleton_doc(long_df: pd.DataFrame) -> str:
    path = stats_models_dir() / "lmm_skeleton_formulas.txt"
    text = """# Proposed LMM formulas (multi-subject SUBALL)

# Python (statsmodels):
# mixed = smf.mixedlm(
#     "RMSE_full ~ C(app) * C(tempo_bpm) + scale(mass_norm)",
#     data=df,
#     groups=df["sub"],
#     re_formula="~1",
# )

n_rows_template = %d
n_subjects_in_template = %d
""" % (
        len(long_df),
        long_df["sub"].nunique(),
    )
    path.write_text(text, encoding="utf-8")
    return str(path)


def stack_suball_long(namecodes: Optional[Iterable[str]] = None) -> pd.DataFrame:
    if namecodes is None:
        roster = suball_namecodes()
        namecodes = [r["namecode"] for r in roster]
    frames: List[pd.DataFrame] = []
    for nc in namecodes:
        try:
            frames.append(build_long_ehf_rmse(nc))
        except FileNotFoundError as e:
            print(f"[skip] LMM long {nc}: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fit_lmm_ehf_rmse(long_df: pd.DataFrame, *, min_subjects: int = 2) -> dict:
    """Fit MixedLM on Resultant RMSE for SUBALL; write FE/RE CSVs."""
    try:
        import statsmodels.formula.api as smf
    except ImportError:
        return {"error": "statsmodels not installed"}

    n_sub = int(long_df["sub"].nunique()) if not long_df.empty else 0
    if n_sub < min_subjects:
        return {"error": f"need >= {min_subjects} subjects, got {n_sub}"}

    sub = long_df[long_df["axis"] == "Resultant"].copy()
    sub = sub[sub["app"].astype(str) != "MeasuredEHF"]
    sub = sub.dropna(subset=["RMSE_full", "mass_norm", "tempo_bpm", "app", "sub"])
    if sub.empty:
        return {"error": "no usable Resultant rows"}

    # z-score mass_norm for scale()
    mu = float(sub["mass_norm"].mean())
    sd = float(sub["mass_norm"].std(ddof=0)) or 1.0
    sub["mass_norm_z"] = (sub["mass_norm"] - mu) / sd

    formula = "RMSE_full ~ C(app) + C(tempo_bpm) + mass_norm_z"
    try:
        model = smf.mixedlm(formula, data=sub, groups=sub["sub"], re_formula="~1").fit(
            reml=True, method="lbfgs"
        )
    except Exception as e:
        return {"error": f"MixedLM failed: {e}"}

    # If RE singular, keep FE table but flag
    singular = False
    try:
        cov = np.asarray(model.cov_re, dtype=float)
        singular = bool(np.linalg.matrix_rank(cov) < cov.shape[0])
    except Exception:
        singular = True

    fe = model.fe_params.rename("coef").to_frame()
    fe["se"] = model.bse_fe
    fe["z"] = model.tvalues
    fe["p"] = model.pvalues
    fe_path = stats_models_dir() / "LMM_EHF_Resultant_RMSE_SUBALL_FE.csv"
    fe.to_csv(fe_path)

    re_path = stats_models_dir() / "LMM_EHF_Resultant_RMSE_SUBALL_RE.txt"
    re_path.write_text(str(model.cov_re) + "\n" + str(model.summary()), encoding="utf-8")

    long_path = stats_long_dir() / "lmm_long_EHF_RMSE_SUBALL.csv"
    sub.to_csv(long_path, index=False)
    return {
        "fe": str(fe_path),
        "re": str(re_path),
        "long": str(long_path),
        "n_sub": n_sub,
        "n_obs": len(sub),
        "converged": bool(getattr(model, "converged", True)),
        "re_singular": singular,
        "formula": formula,
    }


def process_subject(namecode: str) -> dict:
    long_df = build_long_ehf_rmse(namecode)
    rp = result_paths(namecode)
    long_path = stats_long_dir() / f"lmm_long_template_EHF_RMSE_{rp.sub_label}.csv"
    long_df.to_csv(long_path, index=False)
    # legacy flat location
    legacy_long = _stats_dir() / f"lmm_long_template_EHF_RMSE_{rp.sub_label}.csv"
    long_df.to_csv(legacy_long, index=False)
    desc = descriptives_sub7(long_df)
    desc_path = _stats_dir() / f"{rp.sub_label}_rmse_by_factor.csv"
    desc.to_csv(desc_path, index=False)
    ols_path = try_fixed_ols(long_df)
    skel = lmm_skeleton_doc(long_df)
    return {
        "long": str(long_path),
        "descriptives": str(desc_path),
        "ols": ols_path,
        "skeleton": skel,
    }


def process_suball_lmm() -> dict:
    stacked = stack_suball_long()
    if stacked.empty:
        return {"error": "no SUBALL long data"}
    return fit_lmm_ehf_rmse(stacked, min_subjects=2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namecode", default="260526_PJH")
    ap.add_argument("--suball-lmm", action="store_true")
    args = ap.parse_args()
    if args.suball_lmm:
        print(process_suball_lmm())
    else:
        print(process_subject(args.namecode))


if __name__ == "__main__":
    main()

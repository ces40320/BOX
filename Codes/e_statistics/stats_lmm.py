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
from stats_io import stats_long_dir, stats_models_dir, suball_namecodes  # noqa: E402


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


def _p_stars(p: float) -> str:
    if not np.isfinite(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def try_fixed_ols(long_df: pd.DataFrame) -> str:
    try:
        import statsmodels.formula.api as smf
    except ImportError:
        return "statsmodels not installed; skip OLS"

    sub = long_df[long_df["axis"] == "Resultant"].copy()
    if sub.empty:
        return "no Resultant rows"
    sub = sub[sub["app"].astype(str) != "MeasuredEHF"]
    if sub.empty:
        sub = long_df[long_df["axis"] == "Resultant"].copy()
    model = smf.ols(
        "RMSE_full ~ C(app) * C(tempo_bpm) * C(mass_kg) + C(hand)",
        data=sub,
    ).fit()
    sub_label = str(sub["sub"].iloc[0])
    out = stats_models_dir() / f"{sub_label}_OLS_Resultant_RMSE.txt"
    out.write_text(model.summary().as_text(), encoding="utf-8")

    # Clean coefficient table for reports
    rows = []
    for name in model.params.index:
        p = float(model.pvalues.get(name, float("nan")))
        rows.append(
            {
                "Names": str(name),
                "Estimate": float(model.params[name]),
                "SE": float(model.bse[name]),
                "t": float(model.tvalues[name]),
                "p": p,
                "sig": _p_stars(p),
            }
        )
    coef = pd.DataFrame(rows)
    coef_path = stats_models_dir() / f"{sub_label}_OLS_Resultant_RMSE_coefs.csv"
    coef.to_csv(coef_path, index=False)
    sig = coef[(coef["sig"].isin(["*", "**", "***"])) & (~coef["Names"].str.contains("Intercept", case=False))]
    sig.to_csv(stats_models_dir() / f"{sub_label}_OLS_Resultant_RMSE_significant.csv", index=False)

    # Omnibus-style ANOVA table (Type II)
    try:
        from statsmodels.stats.anova import anova_lm

        aov = anova_lm(model, typ=2)
        aov = aov.reset_index().rename(columns={"index": "Effect"})
        aov["sig"] = [_p_stars(float(p)) if pd.notna(p) else "" for p in aov["PR(>F)"]]
        aov.to_csv(stats_models_dir() / f"{sub_label}_OLS_Resultant_RMSE_Omnibus.csv", index=False)
    except Exception:
        pass
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


def _wald_omnibus_table(model) -> pd.DataFrame:
    """jamovi-like Fixed Effects Omnibus from MixedLM Wald tests."""
    from scipy import stats as sps

    rows = []
    try:
        wt = model.wald_test_terms(skip_single=False, scalar=True)
    except TypeError:
        wt = model.wald_test_terms(skip_single=False)

    try:
        if hasattr(wt, "summary_frame"):
            df = wt.summary_frame()
            if df is not None and not df.empty:
                df = df.reset_index()
                name_col = df.columns[0]
                for _, r in df.iterrows():
                    term = str(r[name_col])
                    if term.lower() in ("intercept", "const"):
                        continue
                    # find columns flexibly
                    chi2 = None
                    p = None
                    dfc = None
                    for c in df.columns:
                        cl = str(c).lower()
                        if chi2 is None and ("stat" in cl or "chi" in cl or cl == "f"):
                            chi2 = r[c]
                        if p is None and ("p" in cl):
                            p = r[c]
                        if dfc is None and ("df" in cl):
                            dfc = r[c]
                    chi2_f = float(np.asarray(chi2).reshape(-1)[0]) if chi2 is not None else float("nan")
                    p_f = float(np.asarray(p).reshape(-1)[0]) if p is not None else float("nan")
                    df_f = float(np.asarray(dfc).reshape(-1)[0]) if dfc is not None else float("nan")
                    if not np.isfinite(p_f) and np.isfinite(chi2_f) and np.isfinite(df_f):
                        p_f = float(sps.chi2.sf(chi2_f, df_f))
                    rows.append(
                        {
                            "Effect": term.replace("C(", "").replace(")", ""),
                            "chi2": chi2_f,
                            "df": df_f,
                            "p": p_f,
                            "sig": _p_stars(p_f),
                        }
                    )
                return pd.DataFrame(rows)
    except Exception:
        pass

    # Fallback: parse .table
    try:
        table = wt.table
        for term in table.index:
            if str(term).lower() in ("intercept", "const"):
                continue
            chi2_f = float(np.asarray(table.loc[term, "statistic"]).reshape(-1)[0])
            df_f = float(np.asarray(table.loc[term, "df_constraint"]).reshape(-1)[0])
            p_raw = table.loc[term, "pvalue"] if "pvalue" in table.columns else np.nan
            try:
                p_f = float(np.asarray(p_raw).reshape(-1)[0])
            except Exception:
                p_f = float("nan")
            if not np.isfinite(p_f) and np.isfinite(chi2_f) and np.isfinite(df_f) and df_f > 0:
                p_f = float(sps.chi2.sf(max(chi2_f, 0.0), df_f))
            rows.append(
                {
                    "Effect": str(term).replace("C(", "").replace(")", ""),
                    "chi2": chi2_f,
                    "df": df_f,
                    "p": p_f,
                    "sig": _p_stars(p_f),
                }
            )
    except Exception as e:
        rows.append(
            {"Effect": f"(wald failed: {e})", "chi2": np.nan, "df": np.nan, "p": np.nan, "sig": ""}
        )
    return pd.DataFrame(rows)


def fit_lmm_ehf_rmse(long_df: pd.DataFrame, *, min_subjects: int = 2) -> dict:
    """Fit MixedLM on Resultant RMSE for SUBALL; jamovi-style tables under models/."""
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

    mu = float(sub["mass_norm"].mean())
    sd = float(sub["mass_norm"].std(ddof=0)) or 1.0
    sub["mass_norm_z"] = (sub["mass_norm"] - mu) / sd

    # Research factors: app, tempo, mass_norm (+ two-way interactions). Random: (1|sub)
    formula = (
        "RMSE_full ~ C(app) * C(tempo_bpm) + C(app) * mass_norm_z + C(tempo_bpm) * mass_norm_z"
    )
    try:
        model = smf.mixedlm(formula, data=sub, groups=sub["sub"], re_formula="~1").fit(
            reml=True, method="lbfgs"
        )
    except Exception:
        # fallback: main effects only
        formula = "RMSE_full ~ C(app) + C(tempo_bpm) + mass_norm_z"
        try:
            model = smf.mixedlm(formula, data=sub, groups=sub["sub"], re_formula="~1").fit(
                reml=True, method="lbfgs"
            )
        except Exception as e:
            return {"error": f"MixedLM failed: {e}"}

    singular = False
    try:
        cov = np.asarray(model.cov_re, dtype=float)
        singular = bool(cov.size == 0 or np.linalg.matrix_rank(cov) < max(cov.shape[0], 1))
        # also treat near-zero group variance as singular for reporting
        if float(np.squeeze(cov)) < 1e-8:
            singular = True
    except Exception:
        singular = True

    prefix = "LMM_EHF_Resultant_RMSE_SUBALL"
    model_dir = stats_models_dir()

    # Model Info (jamovi Model Info)
    info = pd.DataFrame(
        [
            {"Info": "Model Type", "Value": "Linear Mixed Model (Gaussian y)"},
            {"Info": "Model", "Value": f"lmer {formula} + (1 | sub)"},
            {"Info": "Dependent", "Value": "EHF Resultant RMSE_full (vs MeasuredEHF)"},
            {"Info": "Fixed effects", "Value": "app, tempo_bpm, mass_norm_z (+ 2-way interactions if fitted)"},
            {"Info": "Random effects", "Value": "(1 | sub)"},
            {"Info": "Sample size (n_obs)", "Value": str(len(sub))},
            {"Info": "N groups (sub)", "Value": str(n_sub)},
            {"Info": "Converged", "Value": str(bool(getattr(model, "converged", True)))},
            {"Info": "RE singular / boundary", "Value": str(singular)},
            {"Info": "Optimizer", "Value": "lbfgs (statsmodels MixedLM)"},
            {"Info": "DF / p method", "Value": "Wald z (approx.; jamovi often uses Satterthwaite)"},
        ]
    )
    info_path = model_dir / f"{prefix}_ModelInfo.csv"
    info.to_csv(info_path, index=False)

    # Fixed Effects Omnibus
    omnibus = _wald_omnibus_table(model)
    omnibus_path = model_dir / f"{prefix}_Omnibus.csv"
    omnibus.to_csv(omnibus_path, index=False)

    # Parameter Estimates
    names = model.fe_params.index.astype(str)
    est = model.fe_params.reindex(model.fe_params.index)
    se = getattr(model, "bse_fe", None)
    if se is None:
        se = pd.Series(np.nan, index=model.fe_params.index)
    else:
        se = pd.Series(se, index=model.fe_params.index).reindex(model.fe_params.index)
    zv = getattr(model, "tvalues", None)
    if zv is None:
        zv = pd.Series(np.nan, index=model.fe_params.index)
    else:
        zv = pd.Series(zv, index=getattr(zv, "index", model.fe_params.index)).reindex(
            model.fe_params.index
        )
    pv = getattr(model, "pvalues", None)
    if pv is None:
        pv = pd.Series(np.nan, index=model.fe_params.index)
    else:
        pv = pd.Series(pv, index=getattr(pv, "index", model.fe_params.index)).reindex(
            model.fe_params.index
        )
    fe = pd.DataFrame(
        {
            "Names": names,
            "Estimate": est.values,
            "SE": se.values,
            "z": zv.values,
            "p": pv.values,
        }
    )
    fe["sig"] = [_p_stars(float(p)) if pd.notna(p) else "" for p in fe["p"]]
    try:
        ci = model.conf_int()
        ci = ci.reindex(model.fe_params.index)
        fe["Lower"] = ci.iloc[:, 0].values
        fe["Upper"] = ci.iloc[:, 1].values
    except Exception:
        fe["Lower"] = np.nan
        fe["Upper"] = np.nan
    fe_path = model_dir / f"{prefix}_FE.csv"
    fe.to_csv(fe_path, index=False)

    # Random Components
    try:
        gvar = float(np.squeeze(np.asarray(model.cov_re, dtype=float)))
    except Exception:
        gvar = float("nan")
    scale = float(getattr(model, "scale", float("nan")))
    icc = gvar / (gvar + scale) if np.isfinite(gvar) and np.isfinite(scale) and (gvar + scale) > 0 else float("nan")
    re_tbl = pd.DataFrame(
        [
            {
                "Groups": "sub",
                "Name": "(Intercept)",
                "Variance": gvar,
                "SD": np.sqrt(gvar) if np.isfinite(gvar) and gvar >= 0 else float("nan"),
                "ICC": icc,
            },
            {
                "Groups": "Residual",
                "Name": "Residual",
                "Variance": scale,
                "SD": np.sqrt(scale) if np.isfinite(scale) and scale >= 0 else float("nan"),
                "ICC": float("nan"),
            },
        ]
    )
    re_csv = model_dir / f"{prefix}_RandomComponents.csv"
    re_tbl.to_csv(re_csv, index=False)

    re_path = model_dir / f"{prefix}_RE.txt"
    warn = ""
    if singular:
        warn = (
            "Warning: (Almost) singular / boundary random-effect variance. "
            "Results may be biased; interpret Fixed Effects with caution "
            "(same class of warning as jamovi GAMLj).\n\n"
        )
    re_path.write_text(warn + str(model.cov_re) + "\n" + str(model.summary()), encoding="utf-8")

    long_path = stats_long_dir() / "lmm_long_EHF_RMSE_SUBALL.csv"
    sub.to_csv(long_path, index=False)

    # Significant FE at-a-glance
    sig_fe = fe[(fe["sig"].isin(["*", "**", "***"])) & (~fe["Names"].str.contains("Intercept", case=False))]
    sig_path = model_dir / f"{prefix}_SignificantFE.csv"
    sig_fe.to_csv(sig_path, index=False)

    return {
        "model_info": str(info_path),
        "omnibus": str(omnibus_path),
        "fe": str(fe_path),
        "re": str(re_path),
        "random_components": str(re_csv),
        "significant_fe": str(sig_path),
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
    desc = descriptives_sub7(long_df)
    desc_path = stats_long_dir() / f"{rp.sub_label}_rmse_by_factor.csv"
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

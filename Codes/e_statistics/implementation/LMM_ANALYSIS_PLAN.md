# LMM analysis plan (implementation track)

Status: design — code lives under `Codes/e_statistics/` (not `d_Results_Analysis`).

## Goals

1. **A — LMM skeleton (multi-subject ready)**  
   Random intercept (and optional slope) for `subject`; fixed effects for `mass_kg`, `tempo_bpm`, `height_m` (or z-scored anthropometry), `app` (vs MeasuredEHF), optionally `section` (AB/BC/CA), `hand` (EHF only).

2. **B — SUB7-first fixed / repeated measures**  
   With one subject, fit OLS / repeated-measures ANOVA / paired contrasts on RMSE or peak force without subject random effect; still emit the same long table so LMM can plug in later.

3. **C — Wait for cohort (outline only)**  
   Full LMM reporting after ≥ ~6–8 Asymmetric subjects; power / singular-fit notes in `research/`.

## Inputs (from results pipeline)

- `Analysis/Asymmetric/EHF/{app}/_metrics/RMSE_SUB{n}.csv`
- `Analysis/Asymmetric/L5S1/{app}/_metrics/RMSE_SUB{n}.csv`
- Optional: peak / mean of `p000`–`p100` timeseries per `cond,seg,hand,axis`
- Covariates from `SUB_Info`: `height`, `body_mass`, `sex`, `age`

## Long-table schema (target)

| column | example | notes |
|--------|---------|--------|
| namecode | 260526_PJH | |
| sub | SUB7 | |
| cond | 7kg_10bpm | |
| mass_kg | 7 | |
| tempo_bpm | 10 | |
| section | AB | |
| seg | 1AB | |
| app | postRiCTO | vs MeasuredEHF for RMSE |
| hand | L \| R \| NA | NA for L5S1 |
| axis | ML \| Vertical \| … | |
| metric | RMSE_full \| peak \| mean | |
| value | float | |
| height_mm | 1757 | from SUB_Info |
| body_mass_kg | 71.8 | |

## Model sketches

### Multi-subject LMM (A)

```text
value ~ C(app) * C(mass_kg) * C(tempo_bpm) + scale(height_mm) + (1 | sub)
```

Start simple; add interactions only if justified. Prefer `statsmodels.formula.api.mixedlm` (Python) for repo consistency; R `lme4` notes in `research/`.

### SUB7-only (B)

```text
value ~ C(app) + C(mass_kg) + C(tempo_bpm) + C(section)
```

Cluster-robust SE by `seg` optional; or mean across reps then 2-way ANOVA on mass × tempo within app contrasts vs MeasuredEHF.

## Deliverables (code, later)

- `build_stats_long_table.py` — stack metrics → long CSV  
- `stats_lmm.py` — MixedLM fit + export  
- `stats_fixed_sub7.py` — path B  
- Outputs under `Analysis/Asymmetric/Stats/` (to confirm at implement time)

## Non-goals here

- Replacing SPM1D curve inference (optional later)  
- Changing `d_Results_Analysis` crop/sign rules

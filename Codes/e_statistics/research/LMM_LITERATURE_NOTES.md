# LMM literature & theory notes

For BOX Asymmetric EHF / L5S1 RMSE and peak loading.  
Implementation plans: `../implementation/LMM_ANALYSIS_PLAN.md`.

## 1. Why LMM (not plain ANOVA)

- Repeated cycles nested in subjects → residuals correlated within subject.  
- Unbalanced reps / missing segs (`error_log`) → LMM handles incomplete cells better than classical repeated-measures ANOVA.  
- Separates **population fixed effects** (mass, tempo, method/app, height) from **subject-specific baseline** (random intercept).

### Core formula (conceptual)

\[
y_{ij} = X_{ij}\beta + Z_{ij}b_j + \varepsilon_{ij}, \quad b_j \sim \mathcal{N}(0,G),\ \varepsilon\sim\mathcal{N}(0,R)
\]

- \(j\): subject (`SUB`)  
- \(i\): observation (cond × seg × app × axis × …)  
- \(\beta\): fixed effects; \(b_j\): random effects

### Practical start

1. Random intercept only: `(1 | subject)`  
2. Add random slope for mass or tempo only if n_subjects and likelihood-ratio test support it  
3. Center/scale continuous covariates (height, body mass)

Reference: Bates et al., *Fitting Linear Mixed-Effects Models Using lme4* (JSS / lme4 vignette).

---

## 2. Closely related applied papers

### Lift / carry endurance — LMM with random intercept & slope

Savage et al. (2016). Predicting endurance time in a repetitive lift and carry task using linear mixed models. *PLOS ONE*.  
https://doi.org/10.1371/journal.pone.0158418  

- Fixed: carry mass; random: subject intercept + slope.  
- Shows subject-specific prediction beats fixed-only \(R^2\).  
- **Mapping:** our `mass_kg` / `tempo_bpm` ≈ task load factors; `sub` random intercept analogous.

### Lumbar shear prediction — mixed-effects family

Recent ergonomic modeling of lumbar shear with load, reach, posture, and hierarchical random effects (subject / task / study).  
Example family: *Appl. Sci.* lumbar shear LMM work (2026 open access discussion of load + horizontal reach as stable predictors).  
https://doi.org/10.3390/app16031414  

- **Mapping:** L5S1 Force_AP / Resultant RMSE or peak as \(y\); mass and tempo as fixed; subject RE.

### Repetitive lifting — mixed models over time

Boocock & Mawston-type lifting fatigue studies: mixed models with subject intercept/slope for kinematics and moments over time.  

- **Mapping:** if we later model cycle index as time, use random slope for cycle; for now RMSE aggregated per seg is enough.

### Team-sport internal load — random intercept then slope

LMM comparing objective vs subjective load; started with random intercept, then random slopes; LRT vs OLS.  
PMC: https://pmc.ncbi.nlm.nih.gov/articles/PMC7825485/  

- **Mapping:** compare nested models `app` only vs `app * mass` etc.; report LRT / AIC.

---

## 3. Design recommendations for BOX

| Topic | Recommendation |
|-------|------------------|
| Outcome | Primary: `RMSE_full` (EHF Resultant & L5S1 Force_Resultant); secondary: peak of 101-pt curve |
| Fixed | `C(app)`, `C(mass_kg)`, `C(tempo_bpm)`, optional `scale(height_mm)`, `C(section)`, `C(hand)` |
| Random | `(1 \| sub)` minimum; add slopes after n_sub ≥ ~8 |
| SUB7 alone | Path B fixed model only — do **not** claim LMM subject variance |
| Tempo | 10 vs 16 bpm as categorical factor (not only continuous) |
| App contrast | Treat MeasuredEHF as reference only for absolute outcomes; for RMSE, apps are HeavyHand / pre / post |

---

## 4. Path C (cohort) — brief only

When multiple Asymmetric subjects finish the OpenSim pipeline:

1. Rebuild long table for all `SUB*`  
2. Fit MixedLM; check singularity  
3. Report FE table + ICC (intercept variance / total)  
4. Optional: separate models per axis to avoid huge multivariate LMM

---

## 5. Reading list (minimal)

1. Bates et al. — lme4 vignette / JSS  
2. Savage et al. 2016 PLOS ONE — lift & carry LMM  
3. Applied lumbar shear LMM (DOI 10.3390/app16031414)  
4. Winter / Robertson biomechanics texts — for moment naming consistency (already frozen in STRUCTURE)

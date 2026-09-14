# Statistics report template (Asymmetric / RiCTO)

Fill one instance per subject (or SUBALL).  
Save to: `Analysis/Asymmetric/_stats/reports/SUB{n}_stats_report.md`  
(or `SUBALL_stats_report.md`).

Format mirrors Symmetric AddBiomech jamovi /  
`L5S1 One-way rm ANOVA Reports (F scores, p values).txt`  
plus agreement (absolute error, Bland–Altman) and LMM blocks from  
[`RICTO_RESULTS_REPORT_PLAN.md`](RICTO_RESULTS_REPORT_PLAN.md).

Replace all `{{…}}` placeholders. Delete unused subsections rather than leaving blanks.

---

## 1. Meta

| Field | Value |
|-------|--------|
| Protocol | Asymmetric |
| Subject(s) | {{SUB_LABELS}} ({{namecodes}}) |
| Apps | MeasuredEHF, HeavyHand, preRiCTO, postRiCTO |
| Contact window (GT) | `|Fy_L| + |Fy_R| ≥ 5 N` (vertical only; not resultant) |
| Min contact duration | {{MIN_CONTACT_DUR_S}} s (default 0.30) |
| Resample | 101 points over GT window |
| mass_norm | `box_mass_kg / body_mass_kg` |
| Report date | {{YYYY-MM-DD}} |
| Pipeline / stats git | {{commit_or_note}} |

---

## 2. Methods snapshot

- **RMSE**: Against MeasuredEHF on the shared GT clock; samples outside each app’s own contact definition zero-filled as in STRUCTURE; report `RMSE_full` and quartiles Q1–Q4 (`0–25`, `25–50`, `50–75`, `75–101` %).
- **Timing absolute error**: Grip (onset) and Deposit (offset) vs GT 5 N window. Comparators: RiCTO (`t1`, `t2+d2`) and, when available, box-marker peak pair. Units: seconds. Stratify by `cond` (kg×bpm) and section (AB/BC/CA).
- **Bland–Altman**: Method − GT (or pairwise method contrast as specified below); report bias and 95% LoA.
- **L5S1 peaks**: Per segment Resultant (or specified axis): initial peak = max in 0–50 %; final peak = max in 50–100 %. Outcomes: peak magnitude, peak time (%).
- **one-way rmANOVA**: Within-subject factor = `app`. Sphericity: Mauchly; if violated, Greenhouse–Geisser. Post-hoc: Bonferroni.
- **LMM** (SUBALL subjects only):  
  `value ~ C(app) * C(tempo_bpm) + scale(mass_norm) + (1|sub)`  
  Single-subject Path B: OLS as in existing `SUB*_OLS_Resultant_RMSE.txt`.

---

## 3. Descriptives

### 3.1 EHF RMSE (Resultant)

Source: `_stats/long/…` or `lmm_long_template_EHF_RMSE_{{SUB}}.csv`.

| App | n | RMSE_full mean±SD | Q1 | Q2 | Q3 | Q4 |
|-----|---|-------------------|----|----|----|-----|
| MeasuredEHF | — | — (reference) | | | | |
| HeavyHand | {{n}} | {{m}}±{{sd}} | | | | |
| preRiCTO | | | | | | |
| postRiCTO | | | | | | |

Optional: split by `tempo_bpm`, `mass_kg`, `hand`, `section`.

### 3.2 L5S1 Force_Resultant RMSE

| App | n | RMSE_full mean±SD |
|-----|---|-------------------|
| … | | |

### 3.3 L5S1 peaks (by app)

| Outcome | MeasuredEHF | HeavyHand | preRiCTO | postRiCTO |
|---------|-------------|-----------|----------|-----------|
| Initial peak mag | | | | |
| Final peak mag | | | | |
| Initial peak time (%) | | | | |
| Final peak time (%) | | | | |

---

## 4. Agreement

### 4.1 Timing absolute error

Source: `_stats/long/timing_abserr_*.csv`.

| Method | Event | mean\|err\|±SD (s) | by tempo notes |
|--------|-------|--------------------|----------------|
| RiCTO | Grip | | |
| RiCTO | Deposit | | |
| Box-marker | Grip | | (or N/A — fallback) |
| Box-marker | Deposit | | |

QC: rows with `|err_onset|` or `|err_offset|` > 0.30 s → list under §7.

### 4.2 Bland–Altman

Source: `_stats/models/BlandAltman_*.csv` (+ PNG under same folder or `RiCTO_manuscript/`).

| Contrast | n | Bias | LoA low | LoA high | Figure |
|----------|---|------|---------|----------|--------|
| RiCTO − GT (Grip) | | | | | Fig … |
| RiCTO − GT (Deposit) | | | | | |
| Box-marker − GT (…) | | | | | |

Interpretation (1–3 bullets):

- …

---

## 5. Inferential

### 5.1 one-way rmANOVA (L5S1 peaks)

Mirror Symmetric report tone:

```text
{{Direction or section}} initial peak time
F({{df1}}, {{df2}}) = {{F}}, p = {{p}}		{{significant|non-significant}}

{{…}} initial peak mag.
F(…) = …, p = …		…

{{…}} final peak time
…

{{…}} final peak mag.
…
```

**Sphericity** (per outcome): Mauchly W = …, p = …; GG ε = …; correction applied: {{none|GG}}.

**Post-hoc (Bonferroni)** — example row:

| Contrast | Mean diff | SE | t | p_bonf |
|----------|-----------|----|---|---------|
| MeasuredEHF − HeavyHand | | | | |
| MeasuredEHF − preRiCTO | | | | |
| MeasuredEHF − postRiCTO | | | | |
| HeavyHand − postRiCTO | | | | |

Raw tables: `_stats/models/rmANOVA_*.csv`.

### 5.2 OLS (single subject, Path B)

If only one subject in this report:

- File: `_stats/SUB{{n}}_OLS_Resultant_RMSE.txt` (or models/)
- Formula: `RMSE_full ~ C(app)*C(tempo_bpm)*C(mass_kg)+C(hand)` (EHF Resultant)
- Summary (paste key coefficients / F tests):

```text
{{paste or brief bullets}}
```

### 5.3 LMM (SUBALL only)

Skip this section for single-subject reports.

- Cohort: subjects on SUBALL roster (`pipeline_progress` all_done + on-disk CSVs)
- Formula: `value ~ C(app) * C(tempo_bpm) + scale(mass_norm) + (1|sub)`
- Outcome: {{RMSE_full | timing_abserr | …}}
- Fixed effects table (source `_stats/models/LMM_*.csv`):

| Term | Coef | SE | z/t | p |
|------|------|----|-----|---|
| … | | | | |

- Random effects: Var(sub) = …; residual = …
- Singular fit / warnings: {{none | note}}

---

## 6. Figures

Link relative to `Analysis/Asymmetric/` (or absolute Dropbox path if needed).

| ID | Path | Notes |
|----|------|-------|
| Fig-RiCTO-1 | `_figures/RiCTO_manuscript/Fig-RiCTO-1.png` | w*(t) triplet |
| Fig-RiCTO-2 | `_figures/RiCTO_manuscript/Fig-RiCTO-2.png` | timing abs err |
| Fig-EHF-1 | `_figures/RiCTO_manuscript/Fig-EHF-1.png` | Resultant + RMSE Q |
| Fig-L5S1-1 | `_figures/RiCTO_manuscript/Fig-L5S1-1.png` | Force_Resultant |
| Fig-L5S1-2 | `_figures/RiCTO_manuscript/Fig-L5S1-2.png` | peaks + ANOVA marks |

Pipeline regenerable copies may also live under `_figures/EHF|L5S1/…`.

---

## 7. QC

| Check | Result |
|-------|--------|
| Timing `|err| > 0.30 s` segments | {{list or none}} |
| Missing MeasuredEHF contact window | {{list or none}} |
| error_log / excluded segs | {{list or none}} |
| LMM singular / non-convergence | {{n/a or note}} |
| Marker timing unavailable (fallback used) | {{yes/no}} |

---

## 8. Take-home (optional, short)

- …
- …

---

## Appendix — Symmetric format reference (do not copy app labels)

Example tone from AddBiomech ANOVA txt:

```text
Lifting initial peak mag.
F(1.45, 27.49) = 211, p < 0.001		significant
```

jamovi omv columns historically: `rms_app*`, `max_app*`, `pktime_app*` for APP1/2/4.  
Asymmetric reports use **MeasuredEHF / HeavyHand / preRiCTO / postRiCTO** names only.

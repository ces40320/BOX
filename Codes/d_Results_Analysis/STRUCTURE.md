# Analysis/Asymmetric output structure (frozen)

Primary subject for v1: `260526_PJH` → SUB7. Multi-subject via `SUB_Info`.
Plan mirror: `.cursor/plans/structure-plan_0480c84a.plan.md`

## Root

```text
Analysis/Asymmetric/
  EHF/{app}/{ML|Vertical|AP|Resultant}/SUB{n}_{L|R}_{AB|BC|CA}.csv
  EHF/{app}/_metrics/{resample_scale|RMSE}_SUB{n}.csv
  L5S1/{app}/{Force_AP|Force_Vertical|Force_ML|Force_Resultant|
              Moment_LateralBending|Moment_AxialRotation|Moment_FlexionExtension}/SUB{n}_{AB|BC|CA}.csv
  L5S1/{app}/_metrics/{resample_scale|RMSE}_SUB{n}.csv
  Residual/{app}/{Fx|Fy|Fz}/SUB{n}_{AB|BC|CA}.csv
  Residual/{app}/_metrics/{resample_scale|Hicks}_SUB{n}.csv
  _figures/{EHF|L5S1|Residual}/
    SUB{n}/                         # subject pooled (all conds)
      SUB{n}_{stem}.png
      {kg_bpm}/                     # per-condition
        SUB{n}_{kg_bpm}_{stem}.png
    SUBALL/                         # pipeline all_done subjects only
      SUBALL_roster.xlsx            # as_of, subjects, n_samples per cond
      SUBALL_{stem}.png
      {kg_bpm}/SUBALL_{kg_bpm}_{stem}.png
```

Apps: `MeasuredEHF`, `HeavyHand`, `preRiCTO`, `postRiCTO`.

`SUBALL` eligibility: `OpenSim_Process/_Main_/Asymmetric/pipeline_progress.xlsx`
Summary `all_done` (all 4 apps complete, no trouble) **and** on-disk analysis
CSVs for every app. Refresh progress with
`python Codes/c_Run_Tools/update_pipeline_progress.py`.
Rebuild figures only: `python run_all_analysis.py --suball-only`.

## Timeseries CSV

- Columns: `cond`, `seg`, `p000`…`p100` (101 pts).
- **AB/BC/CA = separate files**; all `kg_bpm` conditions stacked in one file, sorted by `cond` then `seg`.
- One file per subject × section (× hand for EHF).
- Crop: MeasuredEHF `|Fy_L|+|Fy_R| ≥ 5 N` contact window; cubic resample to 101.
- **`scale_ratio = 101 / n_raw`** (upsample factor; 16 bpm typically **larger** than 10 bpm). Also store `sec_per_pct = duration_s / 100`.
- Error-log segments excluded.

## Sign (report frame; not OpenSim MOT rewrite)

- ML: left (force3) × −1 → Lateral(+); right unchanged.
- AP: both hands × −1 → Anterior(+).
- Vertical: unchanged (down = −).

## L5S1 OpenSim columns

- Force: `L5_S1_IVDjnt_on_lumbar5_in_lumbar5_f{x,y,z}` → AP / Vertical / ML.
- Moment: `…_m{x,y,z}` → LateralBending / AxialRotation / FlexionExtension.

## Frozen decisions

- `scale_ratio = 101 / n_raw` (16 bpm → larger scaling).
- AB/BC/CA: **split files**; kg_bpm: **merge** with leading `cond` column.
- RMSE + resample_scale (+ Hicks for Residual) under `{app}/_metrics/`.
- Figures: generate with CSV when `--plot`; disable with `--no-plot`. Arial; apps on one axes; MeasuredEHF black dashed, HeavyHand red, preRiCTO orange, postRiCTO blue.
- Hicks net force = FP1+FP2+hand3+hand4 from MeasuredEHF ExtLoad.
- Run: `python run_all_analysis.py --namecode 260526_PJH [--plot]`

## RiCTO (under Asymmetric)

```text
Analysis/Asymmetric/RiCTO/
  Summary/SUB{n}_RiCTO_report.xlsx     # flat; auto-updated after optimize
  TimeSeries/SUB{n}/{cond}/*_timeseries.csv
  _validation/                         # validate_ricto long tables + solver_compare
```

No `Results/` or `_synthetic/`. Optimization upserts Summary xlsx (SO/JR not required).
Report sheets: `by_segment`, `by_condition`, `timing_error_summary`.
Timing QC: `|err_onset|` or `|err_offset|` > 0.30 s → `qc_warning`.

## Statistics (separate)

LMM / 추론 통계는 **`Codes/e_statistics/`** 전용.

- `e_statistics/implementation/` — 코드 구현용 분석·설계 MD
- `e_statistics/research/` — 사전 연구·문헌 노트
- 실행 코드: `e_statistics/stats_lmm.py`, `run_statistics.py`
- Results 보고 계획(플롯·시트·통계 MD·정장 경로):  
  [`../e_statistics/implementation/RICTO_RESULTS_REPORT_PLAN.md`](../e_statistics/implementation/RICTO_RESULTS_REPORT_PLAN.md)
- 통계 보고서 템플릿:  
  [`../e_statistics/implementation/STATS_REPORT_TEMPLATE.md`](../e_statistics/implementation/STATS_REPORT_TEMPLATE.md)
- 산출 루트: `Analysis/Asymmetric/_stats/` (`long/`, `models/`, `reports/`)

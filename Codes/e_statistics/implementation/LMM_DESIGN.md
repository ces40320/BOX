# Implementation design notes (LMM)

Fill in during coding. Keep in sync with `LMM_ANALYSIS_PLAN.md`.

## Dependencies

- pandas, numpy, statsmodels (`MixedLM`), scipy  
- Optional: pingouin for RM-ANOVA on path B

## Modules (planned)

| file | role |
|------|------|
| `build_stats_long_table.py` | Read Asymmetric `_metrics` + SUB_Info → long CSV |
| `stats_fixed_sub7.py` | Path B: fixed effects / contrasts for one subject |
| `stats_lmm.py` | Path A: MixedLM API + CSV of FE/RE |
| `run_statistics.py` | CLI entry `--namecode` / `--all` |

## CLI sketch

```bash
cd Codes/e_statistics
python run_statistics.py --namecode 260526_PJH --mode fixed
python run_statistics.py --mode lmm --min-subjects 2   # refuses if n_sub < min
```

## QC

- Drop `error_log` segs (already absent from metrics if results pipeline followed STRUCTURE)  
- Singular fit → fall back to random intercept only; log warning  
- Never treat MeasuredEHF RMSE vs itself as a row

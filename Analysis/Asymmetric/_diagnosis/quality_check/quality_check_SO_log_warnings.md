# SO opensim.log warnings on freeze failures

Scanned preserved logs from `pipeline_trouble.json` (`opensim.log preserved at: …`). Readable fail logs: **0/234**.

Detail CSV: `quality_check_SO_log_warnings.csv`.

## What warnings appear (not VTP / not Performance lines)

- **unable to equilibrate muscles (Thelen2003Muscle)**: in 0/0 logs (0.0%), 0 message(s) total
- **Fiber length is nan**: in 0/0 logs (0.0%), 0 message(s) total
- **Solution error exceeds tolerance**: in 0/0 logs (0.0%), 0 message(s) total
- **wrap-related**: in 0/0 logs (0.0%), 0 message(s) total
- **path length**: in 0/0 logs (0.0%), 0 message(s) total
- **other muscle warnings**: in 0/0 logs (0.0%), 0 message(s) total

Classic “muscle path / wrap exceeded” strings were **rare or absent** in these freeze logs. The dominant muscle-related warning is **`AnalyzeTool::run() unable to equilibrate muscles`** (Thelen `computeInitialFiberEquilibrium`), often with **`Fiber length is nan`**.

## Relation to residual / L5 hypotheses

- **Not a clean “path wrap exceeded” story** in the freeze corpus we have.
- Equilibrate / fiber-NaN **does** show up on a subset of freezes and can sit near `freeze_s` — that points to **muscle state / geometry at that pose** (fiber equilibrium), which can be *downstream of* extreme kinematics or wrapping, but the log text is equilibrate/NaN rather than an explicit path-length exceed flag.
- **`residual_pelvis_list` overload remains universal** on successful SO too (ID≈SO 1:1, always >80 Nm). Equilibrate warnings are therefore a **parallel or aggravating** failure mode for some stalls, not a replacement for the residual finding.
- If equilibrate rate ≪ 100% of freezes, residual/ExtLoad/timing still explain the majority; if ≈100% and tightly time-locked to freeze, muscle equilibrium is the proximate crash reason even when residual is also high.

## Success comparison caveat

Successful SO runs normally delete their temp `opensim_run_*` directories, so we lack a matched success-log corpus. Leftover CWD/`opensim.log` files are only weak controls. A definitive fail-vs-success warning rate needs either log archival on success or a small deliberate re-run sample.

# Code freeze audit (independent)

**Date:** 2026-09-12  
**Repo:** `C:\Users\ok\Documents\GitHub\BOX`  
**Live PID:** 7632 (`run_opensim_pipeline.py --namecode 260526_PJM --tools so,jr --apps MeasuredEHF,preRiCTO,postRiCTO --workers 12 --skip-existing`)  
**PID start:** 2026-09-12 **09:07:47** (+0900)  
**Do not kill:** pipeline left running.

---

## Verdict (first)

**We did not break the pipeline with a code change that forces synchronized SO freezes at the same simulation second.**

- The “Wave1 all froze at sim **4.24**” claim is a **shared-`opensim.log` reporting artifact** (category **A**, with a real multi-worker stall pattern **C** — cohort went quiet, but **not** proven same sim-time per trial).
- Evening commits (`c474edb` subject pool, `3e744ee` / `674490f` max-tasks CLI) and this session’s uncommitted cwd/freeze edits are **not** the cause of the live Wave1/Wave2 hangs.
- Stalls look like **OpenSim StaticOptimization hangs** (muscle equilibrate warnings + 30 min tool timeout), amplified by **12 parallel AnalyzeTools**, not a Python shared lock / SET↔RUN regression.

---

## Evidence

### 1) Timeline vs running process

| Event | When |
|--------|------|
| PID 7632 start (modules loaded by parent) | **09:07** |
| Last `c_Run_Tools` commit *before* start | `b176d87` (30 min AnalyzeTool timeout) and earlier |
| `674490f` / `3e744ee` / `c474edb` (worker pool CLI + subject-shared pool) | **17:20–20:20** (after PID start) |
| Uncommitted cwd + `freeze_sim_time` edits | handlers/pipeline mtime **~22:23–22:24** |
| Current spawn workers / Analyze grandchildren | started **~22:07** (before uncommitted edit) |

- Parent still runs the **09:07** orchestration (condition-scoped pool as of that morning), not the post-`c474edb` subject-wide queue.
- `ProcessPoolExecutor(spawn)` + `max_tasks_per_child=1` means **new workers re-import from disk**, but:
  - Current workers (**22:07**) predate uncommitted handlers (**22:23**) → still **no** `cwd=workdir`.
  - Confirmed: manifests are `TEMP\opensim_jobs_*.json` (HEAD behavior); **no** `opensim_run_*` workdirs; live writes still go to `C:\Users\ok\opensim.log`.

### 2) Identical `freeze_sim_time` / “all at 4.24”

Re-parse of `C:\Users\ok\opensim.log` for Wave1 window **21:07–21:40**:

- 12× `7kg_10bpm_*_MeasuredEHF` loads at **21:07:50**; **0** `Printing results` in window.
- Performance gap: **952 s** after **21:22:56** last line `time = 4.24` → resume **21:38:48** at `sim=0.01` (next wave after ~30 min timeouts).
- **Last 5 s before stall:** sims `{4.21,4.22,4.23,4.24}` each count **1** → looks like **one** advancing stream ending at 4.24, not 12 workers glued at 4.24.
- **Last 60 s:** interleaved streams (e.g. ~2.63 and ~3.91 advancing together) → multiplexed log; **one** last printed sim ≠ all trials’ freeze times.
- `Performance` lines have **no trial ID**. Prior report attributed the **global last multiplexed sim** to every timed-out trial → **artifact (A)**.
- Cohort-wide silence for ~15 min until timeout is still a **real multi-worker stall pattern (C)**, but cause is not “code forced same sim second.”

### 3) Could this session’s uncommitted edits affect PID 7632?

- **Parent:** no (already imported at 09:07).
- **Already-running pool workers / their handler imports:** no until recycle.
- **Workers spawned *after* the file save:** yes, they would load new `opensim_pipeline_handlers.py` (per-job cwd + freeze parse). Current cohort has **not** done that yet.
- Uncommitted diff is **diagnostic** (isolate logs + record freeze time). It does **not** add locks, shared writers, or hang logic.

### 4) Recent commits that *could* hang everyone together?

Searched `Codes/c_Run_Tools/*.py`: **no** `Lock` / `RLock` / `Manager` / file locks.

| Change | Hang risk for live PJM run |
|--------|----------------------------|
| `b176d87` 30 min subprocess timeout | **Mitigation**, not cause; explains Wave timeouts |
| `c474edb` share workers across conditions | **Not in parent** for PID 7632; API of `_run_one_segment` still compatible for spawn children |
| `674490f`/`3e744ee` max-tasks CLI add/revert | Orchestration-only; HEAD still `max_tasks_per_child=1` |
| Uncommitted cwd/`freeze_sim_time` | Not loaded by current workers; not a hang mechanism |

No evidence of broken SET↔RUN isolation: RUN remains `_run_analyze_subprocess.py` in a separate process (same intent as OLD `*_SET.py` / `*_RUN.py`). SO SET still writes **per-trial** SETUP XML; RUN only loads model + `AnalyzeTool.run()` — no shared model `printToXML` in the RUN path (unlike OLD OneCycle RUN which rewrote `*_Actuator.osim`).

### 5) What *does* explain synchronized-looking stalls?

1. **Reporting:** shared `C:\Users\ok\opensim.log` without trial IDs → false “same sim second.”
2. **Real:** many SO jobs can hang / crawl (equilibrate warnings near stall; 30 min kill; 0 prints in Wave1 window).
3. **Environment:** 12 concurrent OpenSim natives + huge shared log I/O; possible CPU/RAM pressure making a whole wave look “stuck together,” still **not** a repo lock bug.

---

## Classification

| Question | Answer |
|----------|--------|
| Did we break the code? | **No** (for synchronized same-sim freezes) |
| Identical freeze times? | **(A)** artifact of shared rolling log; **(C)** real cohort stall/hangs also happened |
| Uncommitted edits on live PID? | **Typically no**; current workers predate edit; later recycles *would* pick them up |

---

## Recommended next action

1. **Do not revert** `c474edb` / timeout commit as the “freeze bug” — evidence does not support that.
2. **Keep** the uncommitted per-job `cwd` + `freeze_sim_time` plumbing (fixes the artifact).
3. When convenient (after current wave / timeouts), **restart** the pipeline so all workers load isolated logs; then any future freeze times are **per-trial**.
4. If hangs remain with isolated logs, treat as **OpenSim SO / resource** issue: lower `--workers`, inspect per-trial `opensim.log` + equilibrate lines, not a subject-pool revert.
5. Optional: after restart, confirm `TEMP\opensim_run_*\opensim.log` appears per job and home `opensim.log` stops multiplexing SO Performance lines.

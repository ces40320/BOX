# Chest wrap geometric diagnosis & evaluation

Shared by approaches **A** (ellipsoid) and **B** (via points). Keeps
`GeometryPath`; does not touch `wrap_fbp/`.

## Workflow (local Anaconda `osim`)

```bat
conda activate osim
cd Codes\c_Run_Tools\troubleshoot_so

:: 1) Diagnose SUB8 (MeasuredEHF)
python chest_wrap_diag\RUN_chest_wrap_diagnose.py --namecode 260526_PJM --apps MeasuredEHF

:: 2) Plots (no OpenSim required if CSVs exist)
python chest_wrap_diag\RUN_chest_wrap_plots.py --namecode 260526_PJM

:: 3A) Ellipsoid optimize → Analysis/.../chest_wrap/SUB8/A/SUB8_ChestFix.osim
python chest_wrap_A_ellipsoid\RUN_chest_ellipsoid_optimize.py --namecode 260526_PJM --apps MeasuredEHF --limit 8

:: 3B) Via-point fit → .../B/SUB8_ChestVia.osim
python chest_wrap_B_viapoints\RUN_chest_via_fit.py --namecode 260526_PJM --apps MeasuredEHF --limit 8

:: 4) Evaluate each candidate
python chest_wrap_diag\RUN_chest_wrap_evaluate.py --namecode 260526_PJM --variant A --candidate-osim Analysis\Asymmetric\_diagnosis\chest_wrap\SUB8\A\SUB8_ChestFix.osim
python chest_wrap_diag\RUN_chest_wrap_evaluate.py --namecode 260526_PJM --variant B --candidate-osim Analysis\Asymmetric\_diagnosis\chest_wrap\SUB8\B\SUB8_ChestVia.osim

:: 5) SO/JR + decision
python chest_wrap_diag\RUN_so_jr_and_chest_wrap_compare.py --namecode 260526_PJM --variants A,B --limit 4

:: 6) Transplant to other subjects
python chest_wrap_diag\RUN_chest_wrap_generalize.py --source-namecode 260526_PJM --target-namecodes 260519_KMJ --variant A
```

Outputs live under `Analysis/<protocol>/_diagnosis/chest_wrap/<SUB>/{diag,A,B,compare}/`.

## Which trials

Every script defaults to the trials whose SO failure was repaired with a
wrap_fbp trial model (`--from-wrap-fbp`), read from
`Analysis/<protocol>/_diagnosis/wrap_fbp/<SUB>/wrap_fbp_summary*.json` or, if
absent, from the `*_WrapFBP.osim` files in the subject tree. `--from-trouble`
(SO trouble list) and `--all-ik` (every IK.mot) can be added instead or as
well. `--limit` picks trials round-robin across conditions and AB·BC·CA
segments. Baseline lengths always come from the shared scaled model, not from
the `_WrapFBP.osim` trial models.

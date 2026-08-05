# BOX — optimization

Algorithms and pipelines for estimating lumbar (L5/S1) loading during two-handed
asymmetric box lifting **without measuring the external hand force**.

## Layout

```
Algorithms/
  ricto_core.py               RiCTO correction algorithm
Pipelines/
  run_batch_optimization.py   batch transition estimation over repeated trials
  verify_cost_landscape.py    cost-landscape scan over transition onset
Scripts/
  exp_data_utils.py           C3D/TRC/MOT I/O and coordinate utilities
```

## RiCTO

Reconstructing the external hand force (EHF) from hand acceleration makes the
load transfer at grip and release a rectangular, step-like change. That
discontinuity drives excessive muscle co-contraction in static optimization and
over-estimates the L5/S1 joint load.

RiCTO estimates when and how quickly the load is transferred, using only the
vertical residual (`residual_pelvis_ty`) of a model driven by ground reaction
forces, and applies a smoothstep weighting to the reconstructed vertical hand
force so that the transition is continuous.

```
                     hand acceleration x box mass
                                 |
   SO vertical residual  ---->  transition estimate (t1, d1, t2, d2)
                                 |
                        smoothstep weighting
                                 |
                  vertical hand force in the external-load file
                                 |
                          SO / JR  ->  L5/S1 load
```

The measured hand force never enters the optimization; it is only used
afterwards as ground truth when evaluating the estimate.

### Usage

```python
from Algorithms.ricto_core import correct_segment

result = correct_segment(
    residual_time=so_time,        # static-optimization time vector
    residual=so_residual_pelvis_ty,
    acc_time=bk_time,             # body-kinematics time vector
    hand_r_acc=acc_r,             # (N, 3) global hand acceleration
    hand_l_acc=acc_l,
    box_mass_kg=15.0,
    ext_time=mot_time,            # external-load file
    ext_data=mot_array,
    col_index=mot_columns,
)

corrected   = result['corrected']     # RiCTO applied
rectangular = result['rectangular']   # uncorrected reference
params      = result['transition']['params']   # t1, d1, t2, d2
```

Individual steps are also available: `optimize_transition`,
`reconstruct_hand_force`, `apply_correction`, and the weighting curves
`smooth_weight_curve` / `rectangle_weight_curve`.

### Scope

- Only the vertical hand force is modified. Ground reaction forces, horizontal
  hand forces, moments and CoP are left untouched.
- No constant is tied to a particular segment duration, so 6.0 s (10 bpm) and
  3.75 s (16 bpm) segments are handled by the same code path.
- The optimization start value is derived from the residual instead of being
  fixed, and the baseline is an upper-quantile mean rather than an
  initial-window mean.

## Running the pipelines

Data and output locations are read from environment variables, so no path is
hard-coded in the scripts:

| variable | meaning | default |
|---|---|---|
| `BOX_DATA_DIR` | directory holding the input `.sto` files | `./data` |
| `BOX_RESULT_DIR` | directory for result tables | `./results` |

```bash
BOX_DATA_DIR=/path/to/sto python Pipelines/run_batch_optimization.py
BOX_DATA_DIR=/path/to/sto python Pipelines/run_sub2_analysis.py
```

## Requirements

Python 3.10+, `numpy`, `scipy`. OpenSim is required only by the pipelines that
run inverse kinematics, static optimization and joint reaction analysis.

## Model

Lifting Full-Body (LFB) model — Beaucage-Gauvreau et al., *Comput Methods Biomech
Biomed Engin* 22(5), 2019. doi:10.1080/10255842.2018.1564819

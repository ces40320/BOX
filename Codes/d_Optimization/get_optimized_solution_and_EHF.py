from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

BOX_MASS_KG = 15.0
GRAVITY_Y = -9.8065999999999995
RMO_INIT_GUESS = [2.2, 0.4, 4.0, 0.4]
DT_TARGET = 0.001

# ExtLoad .mot variant suffixes (single source for c_Run Tools pipeline)
EXTLOAD_ORIGINAL_SUFFIX = "_estimated_original"
EXTLOAD_CORRECTED_SUFFIX = "_RiCTO-corrected"


def get_extload_base_basename(kg_bpm, trial_num, task_num, app_suffix="APP2"):
    """Base basename for ExtLoad .mot (no variant suffix, no .mot). Used when writing/reading ExtLoad files."""
    return f"{kg_bpm}_trial{trial_num}_12sec_{task_num}_ExtLoad{app_suffix}"


def get_extload_variant_suffixes(app_suffix="APP2"):
    """
    Return (original_suffix, corrected_suffix) derived from the path pattern used in this module.
    c_Run Tools uses this to avoid hardcoding; suffixes are parsed from the same path strings.
    """
    base = get_extload_base_basename("15_10", 1, 1, app_suffix)
    orig_stem = base + EXTLOAD_ORIGINAL_SUFFIX + ".mot"
    corr_stem = base + EXTLOAD_CORRECTED_SUFFIX + ".mot"
    orig_suffix = Path(orig_stem).stem[len(base) :]
    corr_suffix = Path(corr_stem).stem[len(base) :]
    return orig_suffix, corr_suffix


SUB = "SUB1"
TRIAL_FOLDER = "trial15_10_1"
REPS = range(1, 11)

# ROOT_DIR = Path(r"E:\Dropbox\SEL\BOX\Codes\BOX_2_CSM\ICNR")
ROOT_DIR = Path(r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\c_AddBio_Continous")
SOURCE_DIR = ROOT_DIR / SUB / "APP2_OneCycle" / TRIAL_FOLDER

SAVE_DIR = Path(r"E:\Dropbox\SEL\BOX\Analysis\Symmetric\RiCTO")
SAVE_DIR.mkdir(parents=True, exist_ok=True)


def read_opensim_storage(path):
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    end_idx = next(i for i, line in enumerate(lines) if "endheader" in line.lower())

    j = end_idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1

    columns = lines[j].strip().split()
    rows = [ln.strip().split() for ln in lines[j + 1:] if ln.strip()]

    df = pd.DataFrame(rows, columns=columns).apply(pd.to_numeric, errors="coerce")
    df = df.dropna(how="all")

    meta = {
        "path": str(path),
        "header_lines": lines[: end_idx + 1],
        "blank_lines_after_header": lines[end_idx + 1 : j],
        "column_line": lines[j],
    }
    return df, meta


def write_opensim_storage(path, df, meta, float_fmt="%.8f", write_blank_after_header=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for line in meta["header_lines"]:
            f.write(line)
        if write_blank_after_header:
            for line in meta["blank_lines_after_header"]:
                f.write(line)
        f.write("\t".join(df.columns) + "\n")
        df.to_csv(f, sep="\t", index=False, header=False, float_format=float_fmt, lineterminator="\n")


def shift_to_starting_time(df):
    out = df.copy()
    out["time"] = out["time"] - out["time"].iloc[0]
    out["time"] = np.round(out["time"], 10)
    return out



######################### RMO Optimization Functions #########################

#### Optimization Weight Functions Settings ####
def smoothstep_ramp(t, t_start, duration):
    if duration < 0.01:
        return np.where(t >= t_start, 1.0, 0.0)
    tau = (t - t_start) / duration
    tau = np.clip(tau, 0.0, 1.0)
    return 3.0 * tau**2 - 2.0 * tau**3


def smooth_weight_curve(t, params):
    t1, d1, t2, d2 = params
    ramp_up = smoothstep_ramp(t, t1, d1)
    ramp_down = smoothstep_ramp(t, t2, d2)
    return np.clip(ramp_up - ramp_down, 0.0, 1.0)


def rectangle_weight_curve(t, params):
    t1, d1, t2, d2 = params
    t_off = t2 + d2
    return np.where((t >= t1) & (t <= t_off), 1.0, 0.0)


#### RMO Optimization Objective Function ####
def rmo_objective(params, time_arr, residual_raw, baseline, part_end):
    t1, d1, t2, d2 = params
    if (t1 < 0.0) or (t2 > part_end) or (d1 < 0.1) or (d2 < 0.1) or (t1 + d1 >= t2):
        return 1e9
    w_curve = smooth_weight_curve(time_arr, params)
    correction = baseline * (1.0 - w_curve)
    residual_adjusted = residual_raw - correction
    return np.sum(residual_adjusted**2)


#### Run RMO Optimization ####
def optimize_rmo_from_force_sto(force_df):
    force_df = shift_to_starting_time(force_df)

    if "residual_pelvis_ty" not in force_df.columns:
        raise ValueError("Could not find residual_pelvis_ty in force .sto.")

    time_1000 = force_df["time"].to_numpy(dtype=float)
    residual_1000 = force_df["residual_pelvis_ty"].to_numpy(dtype=float)
    part_end = float(time_1000[-1])

    baseline = float(np.mean(residual_1000[time_1000 < 0.5])) if np.any(time_1000 < 0.5) else float(residual_1000[0])

    res = minimize(
        rmo_objective,
        x0=np.array(RMO_INIT_GUESS, dtype=float),
        args=(time_1000, residual_1000, baseline, part_end),
        method="Nelder-Mead",
        options={"maxiter": 5000, "xatol": 1e-6, "fatol": 1e-6},
    )
    if not res.success:
        raise RuntimeError(f"RMO optimization failed: {res.message}")

    params = res.x.astype(float)
    
    return {
        "time_1000": time_1000,                                 # time array    
        "residual_1000": residual_1000,                         # baseline-adjusted residual array 
        "residual_minimized": residual_1000 - baseline * (1.0 - smooth_weight_curve(time_1000, params)),
        "baseline": baseline,                                   # baseline value (mean of residual before 0.5s)
        "params": params,                                       # optimized parameters (t1, d1, t2, d2)
        "smooth_w": smooth_weight_curve(time_1000, params),     # optimized smooth weight function
        "rect_w": rectangle_weight_curve(time_1000, params),    # optimized rectangle weight function
        "cost": float(res.fun),                                 # cost function value (sum of squared residuals)
        "part_end": part_end,                                   # last time point of the half-part (6sec or 12sec)
    }


######################### RMO Optimization Functions (End) #########################



def compute_raw_app2_EHF_from_acc(acc_df, box_mass_kg, gravity_y):
    acc_df = shift_to_starting_time(acc_df)

    required = ["hand_r_X", "hand_r_Y", "hand_r_Z", "hand_l_X", "hand_l_Y", "hand_l_Z"]
    missing = [c for c in required if c not in acc_df.columns]
    if missing:
        raise ValueError(f"Missing ACC columns: {missing}")

    time_1000 = acc_df["time"].to_numpy(dtype=float)
    hand_r_ax = acc_df["hand_r_X"].to_numpy(dtype=float)
    hand_l_ax = acc_df["hand_l_X"].to_numpy(dtype=float)
    
    hand_r_ay = acc_df["hand_r_Y"].to_numpy(dtype=float)
    hand_l_ay = acc_df["hand_l_Y"].to_numpy(dtype=float)
    
    hand_r_az = acc_df["hand_r_Z"].to_numpy(dtype=float)
    hand_l_az = acc_df["hand_l_Z"].to_numpy(dtype=float)


    mass_per_hand = box_mass_kg / 2.0
    raw_fx_r = -(mass_per_hand * hand_r_ax)
    raw_fx_l = -(-(mass_per_hand * hand_l_ax))                  # ML방향 부호 통일을 위해 x방향 왼손만 음수 처리 -> Lateral: (+), Medial: (-)
    
    raw_fy_r = -(mass_per_hand * (hand_r_ay - gravity_y))       # Up: (+), Down: (-)
    raw_fy_l = -(mass_per_hand * (hand_l_ay - gravity_y))       # Up: (+), Down: (-)
    
    raw_fz_r = -(-(mass_per_hand * hand_r_az))                  # AP방향 부호 반전을 위해 z방향 양손 음수 처리 -> Anterior: (+), Posterior: (-)
    raw_fz_l = -(-(mass_per_hand * hand_l_az))                  # AP방향 부호 반전을 위해 z방향 양손 음수 처리 -> Anterior: (+), Posterior: (-)

    return {
        "time_1000": time_1000,
        "raw_fx_r": raw_fx_r,
        "raw_fx_l": raw_fx_l,
        "raw_fy_r": raw_fy_r,
        "raw_fy_l": raw_fy_l,
        "raw_fz_r": raw_fz_r,
        "raw_fz_l": raw_fz_l,
        "part_end": float(time_1000[-1]),
    }


def generate_original_and_corrected_EHF(raw_pack, rmo_pack):
    # force(RMO) time base 기준으로 ACC-derived raw force 보간
    time_target = rmo_pack["time_1000"]

    raw_fy_r = np.interp(time_target, raw_pack["time_1000"], raw_pack["raw_fy_r"])
    raw_fy_l = np.interp(time_target, raw_pack["time_1000"], raw_pack["raw_fy_l"])
    raw_fx_r = np.interp(time_target, raw_pack["time_1000"], raw_pack["raw_fx_r"])
    raw_fx_l = np.interp(time_target, raw_pack["time_1000"], raw_pack["raw_fx_l"])
    raw_fz_r = np.interp(time_target, raw_pack["time_1000"], raw_pack["raw_fz_r"])
    raw_fz_l = np.interp(time_target, raw_pack["time_1000"], raw_pack["raw_fz_l"])

    rect_w = rmo_pack["rect_w"]
    smooth_w = rmo_pack["smooth_w"]

    return {
        "time_1000": time_target,
        "residual_1000": rmo_pack["residual_1000"],
        "residual_shifted": rmo_pack["residual_1000"] - rmo_pack["baseline"],
        "residual_minimized": rmo_pack["residual_minimized"],
        
        "raw_fx_r": raw_fx_r,
        "raw_fx_l": raw_fx_l,
        "raw_fy_r": raw_fy_r,
        "raw_fy_l": raw_fy_l,
        "raw_fz_r": raw_fz_r,
        "raw_fz_l": raw_fz_l,
        
        "orig_fx_r": raw_fx_r * rect_w,
        "orig_fx_l": raw_fx_l * rect_w,
        "orig_fy_r": raw_fy_r * rect_w,
        "orig_fy_l": raw_fy_l * rect_w,
        "orig_fz_r": raw_fz_r * rect_w,
        "orig_fz_l": raw_fz_l * rect_w,
        
        "corr_fy_r": raw_fy_r * smooth_w,
        "corr_fy_l": raw_fy_l * smooth_w,
        
        "rect_w": rect_w,
        "smooth_w": smooth_w,
        "params": rmo_pack["params"],
        "baseline": rmo_pack["baseline"],
        "cost": rmo_pack["cost"],
    }


def shift_time(pack, offset):
    out = {}
    for k, v in pack.items():
        if k == "time_1000":
            out[k] = np.round(v + offset, 10)
        else:
            out[k] = v
    return out


def combine_parts(pack1, pack2):
    combined = {}
    for key in pack1.keys():
        if isinstance(pack1[key], np.ndarray):
            combined[key] = np.concatenate([pack1[key], pack2[key]])
        else:
            combined[key] = [pack1[key], pack2[key]]
    return combined


def build_output_dfs(part1_result, part2_result):
    """
    Build output dataframes for the optimized solution and EHF estimates.
    
    Args:
        part1_result: RMO optimization result from the first half of the 12sec OneCycle. (dict, key: time_1000, residual_1000, baseline, params, smooth_w, rect_w, cost, part_end)
        part2_result: RMO optimization result from the second half of the 12sec OneCycle. (dict)
        
    Returns:
        signal_df: Dataframe containing the optimized solution and EHF estimates. (DataFrame, columns: time, rect_w, residual_1000, smooth_w, raw_fx_r, raw_fx_l, raw_fy_r, raw_fy_l, raw_fz_r, raw_fz_l, orig_fy_r, orig_fy_l, corr_fy_r, corr_fy_l)
        summary_df: Dataframe containing the summary of the optimization results. (DataFrame)
    """
    shifted_part2 = shift_time(part2_result, offset=float(part1_result["time_1000"][-1] + DT_TARGET))
    combined = combine_parts(part1_result, shifted_part2)

    signal_df = pd.DataFrame({
        "time": combined["time_1000"],
        "rect_w": combined["rect_w"],
        "smooth_w": combined["smooth_w"],
        
        "residual_shifted": combined["residual_shifted"],
        "residual_minimized": combined["residual_minimized"],
        
        "orig_fx_r": combined["orig_fx_r"],
        "orig_fx_l": combined["orig_fx_l"],
        "orig_fy_r": combined["orig_fy_r"],
        "orig_fy_l": combined["orig_fy_l"],
        "orig_fz_r": combined["orig_fz_r"],
        "orig_fz_l": combined["orig_fz_l"],
        
        "corr_fy_r": combined["corr_fy_r"],
        "corr_fy_l": combined["corr_fy_l"],
        
        "raw_fx_r": combined["raw_fx_r"],
        "raw_fx_l": combined["raw_fx_l"],
        "raw_fy_r": combined["raw_fy_r"],
        "raw_fy_l": combined["raw_fy_l"],
        "raw_fz_r": combined["raw_fz_r"],
        "raw_fz_l": combined["raw_fz_l"],
    })

    summary_df = pd.DataFrame({
        "part": [1, 2],
        "t1": [part1_result["params"][0], part2_result["params"][0]],
        "d1": [part1_result["params"][1], part2_result["params"][1]],
        "t2": [part1_result["params"][2], part2_result["params"][2]],
        "d2": [part1_result["params"][3], part2_result["params"][3]],
        "baseline": [part1_result["baseline"], part2_result["baseline"]],
        "cost": [part1_result["cost"], part2_result["cost"]],
    })
    return signal_df, summary_df


def overwrite_EHF_mot(mot_df, signal_df, mode="corrected"):
    out = mot_df.copy()

    # TrialN absolute time -> relative 0~12
    t_mot = out["time"].to_numpy(dtype=float)
    t_mot_rel = t_mot - t_mot[0]

    if mode == "original":
        fx_r = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fx_r"])
        fx_l = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fx_l"])
        fz_r = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fz_r"])
        fz_l = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fz_l"])
        
        fy_r = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fy_r"])
        fy_l = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fy_l"])
        
    elif mode == "corrected":
        fx_r = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fx_r"])
        fx_l = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fx_l"])
        fz_r = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fz_r"])
        fz_l = np.interp(t_mot_rel, signal_df["time"], signal_df["orig_fz_l"])
        
        fy_r = np.interp(t_mot_rel, signal_df["time"], signal_df["corr_fy_r"])
        fy_l = np.interp(t_mot_rel, signal_df["time"], signal_df["corr_fy_l"])
    else:
        raise ValueError("mode must be original or corrected")

    out["hand_force3_vx"] = fx_r
    out["hand_force3_vy"] = fy_r
    out["hand_force3_vz"] = fz_r
    out["hand_force4_vx"] = fx_l
    out["hand_force4_vy"] = fy_l
    out["hand_force4_vz"] = fz_l

    torque_cols = [
        "hand_torque3_x", "hand_torque3_y", "hand_torque3_z",
        "hand_torque4_x", "hand_torque4_y", "hand_torque4_z"
    ]
    for c in torque_cols:
        if c in out.columns:
            out[c] = 0.0

    return out


def process_trial(trial_num: int):
    
    ################### 1. Data Loading ###################
    # 1st part : 1st half of the 12sec OneCycle
    # 2nd part : 2nd half of the 12sec OneCycle
    
    BKpostsim_dir = SOURCE_DIR /"BK_Results"/"PostSim"
    SOpostsim_dir = SOURCE_DIR /"SO_Results"/"PostSim"
    ExtLoad_dir = ROOT_DIR / SUB / "OneCycle_TrcMot"

    BKacc1_path = BKpostsim_dir / f"SUB1_15_10_1_12sec_{trial_num}_APP2_OneCycle_BK_acc_global_1000Hz_1st_half.sto"
    BKacc2_path = BKpostsim_dir / f"SUB1_15_10_1_12sec_{trial_num}_APP2_OneCycle_BK_acc_global_1000Hz_2nd_half.sto"
    SOresidual1_path = SOpostsim_dir / f"SUB1_15_10_1_12sec_{trial_num}_APP2_OneCycle_StaticOptimization_force_1st_half.sto"
    SOresidual2_path = SOpostsim_dir / f"SUB1_15_10_1_12sec_{trial_num}_APP2_OneCycle_StaticOptimization_force_2nd_half.sto"
    ExtLoad_mot_path = ExtLoad_dir / f"15_10_trial1_12sec_{trial_num}_ExtLoadAPP1.mot"


    #### 1-1. Data Pre-processing ####
    for p in [BKacc1_path, BKacc2_path, SOresidual1_path, SOresidual2_path, ExtLoad_mot_path]:
        if not p.exists():
            raise FileNotFoundError(f"Missing file: {p}")

    acc1, _ = read_opensim_storage(BKacc1_path)   # 1st part ACC data
    acc2, _ = read_opensim_storage(BKacc2_path)   # 2nd part ACC data
    force1, _ = read_opensim_storage(SOresidual1_path)   # 1st part SO data
    force2, _ = read_opensim_storage(SOresidual2_path)   # 2nd part SO data
    mot_df, mot_meta = read_opensim_storage(ExtLoad_mot_path)   # Original External Load data



    ################### 2. EHF (External Hand Force) Calculation (APP2 Estimates) ###################
    # 1st part EHF calculation
    raw1 = compute_raw_app2_EHF_from_acc(acc1, box_mass_kg=BOX_MASS_KG, gravity_y=GRAVITY_Y)
    # 2nd part EHF calculation
    raw2 = compute_raw_app2_EHF_from_acc(acc2, box_mass_kg=BOX_MASS_KG, gravity_y=GRAVITY_Y)
    
    

    ################### 3. RMO Optimization ###################
    # 1st part RMO optimization
    rmo1 = optimize_rmo_from_force_sto(force1)
    # 2nd part RMO optimization
    rmo2 = optimize_rmo_from_force_sto(force2)
    

    #### 3-1. Generate Original and Corrected EHF Estimates ####
    part1 = generate_original_and_corrected_EHF(raw1, rmo1)
    part2 = generate_original_and_corrected_EHF(raw2, rmo2)

    #### 3-2. Build Optimized Solution and EHF (Output: DataFrames) ####
    signal_df, summary_df = build_output_dfs(part1, part2)

    #### 3-3. Write Original and Corrected EHF from Original APP1 MOT File ####
    original_mot = overwrite_EHF_mot(mot_df, signal_df, mode="original")
    corrected_mot = overwrite_EHF_mot(mot_df, signal_df, mode="corrected")


    ################### 4. Save Results ###################
    save_path = SAVE_DIR / f"Trial{trial_num}"
    save_path.mkdir(parents=True, exist_ok=True)
    
    signal_csv = save_path / "RiCTO-Result_WeightFunction_Residual_EHFs.csv"
    summary_csv = save_path / "RiCTO-Result_Solution_Summary.csv"
    base_basename = get_extload_base_basename("15_10", 1, trial_num, "APP2")
    original_ExtLoad_mot_path = ExtLoad_dir / f"{base_basename}{EXTLOAD_ORIGINAL_SUFFIX}.mot"
    corrected_ExtLoad_mot_path = ExtLoad_dir / f"{base_basename}{EXTLOAD_CORRECTED_SUFFIX}.mot"


    signal_df.to_csv(signal_csv, index=False)
    summary_df.to_csv(summary_csv, index=False)
    write_opensim_storage(original_ExtLoad_mot_path, original_mot, mot_meta)
    write_opensim_storage(corrected_ExtLoad_mot_path, corrected_mot, mot_meta)

    return {
        "trial": trial_num,
        "signal_csv": str(signal_csv),
        "summary_csv": str(summary_csv),
        "original_mot": str(original_ExtLoad_mot_path),
        "corrected_mot": str(corrected_ExtLoad_mot_path),
        "raw_fy_r_max": float(np.nanmax(np.abs(signal_df["raw_fy_r"]))),
        "raw_fy_l_max": float(np.nanmax(np.abs(signal_df["raw_fy_l"]))),
        "orig_fy_r_max": float(np.nanmax(np.abs(signal_df["orig_fy_r"]))),
        "orig_fy_l_max": float(np.nanmax(np.abs(signal_df["orig_fy_l"]))),
        "corr_fy_r_max": float(np.nanmax(np.abs(signal_df["corr_fy_r"]))),
        "corr_fy_l_max": float(np.nanmax(np.abs(signal_df["corr_fy_l"]))),
        "status": "ok",
    }


if __name__ == "__main__":
    results = []
    failed = []

    for n in REPS:
        print(f"\n================ Trial {n} ================")
        try:
            res = process_trial(n)
            results.append(res)
            print("Saved:")
            print(res["signal_csv"])
            print(res["summary_csv"])
            print(res["original_mot"])
            print(res["corrected_mot"])
            print("max abs corrected:", res["corr_fy_r_max"], res["corr_fy_l_max"])
        except Exception as e:
            failed.append((n, str(e)))
            print(f"❌ Trial {n} 실패: {e}")

    summary_out = ROOT_DIR / "batch_RiCTO_summary.csv"
    pd.DataFrame(results).to_csv(summary_out, index=False)

    print("\n========================================")
    print(f"Summary saved: {summary_out}")
    if failed:
        print("⚠️ 실패한 trial:")
        for n, msg in failed:
            print(f"  - Trial {n}: {msg}")
    else:
        print("✅ RiCTO 후 External Load MOT 생성 완료!")
#%% import packages and functions
import pandas as pd
import numpy as np
import os
from pathlib import Path
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import spm1d
from scipy import stats

from GripEventDetection_from_Loadcell import load_events_dict, read_opensim_mot
from Utils import normalize_JR_cropped_by_events, normalize_ExtLoad_cropped_by_events


def _read_mot_for_crop(path):
    """OneCycle .mot(OpenSim endheader 형식) → (time_arr, df) for normalize_ExtLoad_cropped_by_events."""
    df = read_opensim_mot(path)
    return df["time"].values, df

def Calculate_RMSE(measured_data, predicted_data, intervals):
    """
    측정값과 추정값 사이의 구간별 RMSE 평균과 표준편차를 계산하는 함수.

    Parameters:
    - measured_data (pd.DataFrame or np.array): 측정된 데이터 (반복 횟수 x 시간 스텝).
    - predicted_data (pd.DataFrame or np.array): 추정된 데이터 (반복 횟수 x 시간 스텝).
    - intervals (list of tuple): 시간 구간을 나타내는 (start, end) 튜플의 리스트.

    Returns:
    - result_dict (dict): 각 구간별 RMSE 평균과 표준편차를 담은 딕셔너리.
    """
    result_dict = {'Interval': [], 'RMSE_Mean': [], 'RMSE_Std': []}

    # 입력 타입이 DataFrame인지 여부를 미리 판단
    is_measured = isinstance(measured_data, pd.DataFrame)
    is_pred_df = isinstance(predicted_data, pd.DataFrame)

    for start, end in intervals:
        # 해당 구간의 데이터 추출 (입력 타입에 따라 분기)
        if is_measured:
            measured_segment = measured_data.iloc[:, start:end].to_numpy()
        else:
            measured_arr = np.asarray(measured_data)
            measured_segment = measured_arr[:, start:end]

        if is_pred_df:
            predicted_segment = predicted_data.iloc[:, start:end].to_numpy()
        else:
            predicted_arr = np.asarray(predicted_data)
            predicted_segment = predicted_arr[:, start:end]

        # 구간별 RMSE 계산 (반복별 RMSE)
        rmse_values = np.sqrt(np.mean((measured_segment - predicted_segment) ** 2, axis=1))

        # 결과 저장
        result_dict['Interval'].append(f"{start}-{end}")
        result_dict['RMSE_Mean'].append(np.mean(rmse_values))
        result_dict['RMSE_Std'].append(np.std(rmse_values))

    return result_dict

# intervals 정의: 4개 구간 (0-25%, 25-50%, 50-75%, 75-100%)
n_points = 101  # 총 시간 스텝 수 (예제)
intervals = [(0, n_points // 4), 
             (n_points // 4, n_points // 2), 
             (n_points // 2, 3 * n_points // 4), 
             (3 * n_points // 4, n_points)]
## 사용 예시
# # 예제 데이터: 측정값과 추정값 (각각 10회 반복 측정)
# measured_df = pd.DataFrame(np.random.rand(10, n_points) * 100)  # 임의의 측정값
# predicted_df = measured_df + pd.DataFrame(np.random.randn(10, n_points) * 10)  # 임의의 추정값
## RMSE 계산
# rmse_results = Calculate_RMSE(measured_df, predicted_df, intervals)
# print("구간별 RMSE:", rmse_results)

def Calculate_Euclidean_Norm(X,Y,Z=None,dim=3):
    """
    Calculate the Euclidean norm of the vector (X, Y, Z).
    
    Input: 2 or 3 np.array of (n_reps, n_points). e.g. (10, 101)
    Output: np.array of (n_reps, n_points)
    """
    if dim == 3:
        return np.sqrt(X**2 + Y**2 + Z**2)
    elif dim == 2:
        return np.sqrt(X**2 + Y**2)
    else:
        raise ValueError(f"Dimension must be 2 or 3, but got {dim}")


def summarize_ricto_timing_vs_loadcell(events_dict, root_dir, sub_name, kg_bpm, trial, ricto_dir):
    """
    Compare loadcell-threshold event timings with RiCTO-optimized timing parameters.

    The loadcell events and RiCTO summaries come from the same 10 trials, so the
    appropriate inferential test is a paired t-test, not an independent t-test.
    """
    extload_dir = Path(root_dir) / sub_name / "OneCycle_TrcMot"
    task_nums = range(1, 11)
    trial_rows = []

    for task_idx in task_nums:
        mot_path = extload_dir / f"{kg_bpm}_trial{trial}_12sec_{task_idx}_ExtLoadAPP1.mot"
        summary_path = Path(ricto_dir) / f"Trial{task_idx}" / "RiCTO-Result_Solution_Summary.csv"

        if not mot_path.exists():
            raise FileNotFoundError(f"Missing APP1 loadcell MOT file: {mot_path}")
        if not summary_path.exists():
            raise FileNotFoundError(f"Missing RiCTO summary file: {summary_path}")

        mot_df = read_opensim_mot(mot_path)
        trial_start = float(mot_df["time"].iloc[0])
        summary_df = pd.read_csv(summary_path)
        if summary_df.shape[0] < 2:
            raise ValueError(f"Expected 2 rows(part 1, 2) in {summary_path}, got {summary_df.shape[0]}")

        up_row = summary_df.iloc[0]
        down_row = summary_df.iloc[1]

        # Elevating events are compared within the first 6 s half, lowering within the second half.
        up_start_detected = float(events_dict["Up_grip"][task_idx - 1] - trial_start)
        up_end_detected = float(events_dict["Up_deposit"][task_idx - 1] - trial_start)
        down_start_detected = float(events_dict["Down_grip"][task_idx - 1] - (trial_start + 6.0))
        down_end_detected = float(events_dict["Down_deposit"][task_idx - 1] - (trial_start + 6.0))

        trial_rows.append({
            "trial": task_idx,
            "up_start_detected": up_start_detected,
            "up_end_detected": up_end_detected,
            "down_start_detected": down_start_detected,
            "down_end_detected": down_end_detected,
            "up_start_opt": float(up_row["t1"]),
            "up_end_opt": float(up_row["t2"] + up_row["d2"]),
            "down_start_opt": float(down_row["t1"]),
            "down_end_opt": float(down_row["t2"] + down_row["d2"]),
            "up_d1_opt": float(up_row["d1"]),
            "up_d2_opt": float(up_row["d2"]),
            "down_d1_opt": float(down_row["d1"]),
            "down_d2_opt": float(down_row["d2"]),
        })

    comparison_df = pd.DataFrame(trial_rows)

    test_pairs = {
        "Elevating onset": ("up_start_detected", "up_start_opt"),
        "Elevating end": ("up_end_detected", "up_end_opt"),
        "Lowering onset": ("down_start_detected", "down_start_opt"),
        "Lowering end": ("down_end_detected", "down_end_opt"),
    }

    summary_rows = []
    for metric, (detected_col, opt_col) in test_pairs.items():
        detected = comparison_df[detected_col].to_numpy(dtype=float)
        optimized = comparison_df[opt_col].to_numpy(dtype=float)
        diff = optimized - detected
        ttest = stats.ttest_rel(detected, optimized, nan_policy="omit")

        summary_rows.append({
            "metric": metric,
            "detected_mean_s": float(np.nanmean(detected)),
            "detected_sd_s": float(np.nanstd(detected, ddof=1)),
            "optimized_mean_s": float(np.nanmean(optimized)),
            "optimized_sd_s": float(np.nanstd(optimized, ddof=1)),
            "mean_difference_opt_minus_detected_s": float(np.nanmean(diff)),
            "mae_s": float(np.nanmean(np.abs(diff))),
            "paired_t_stat": float(ttest.statistic),
            "paired_t_pvalue": float(ttest.pvalue),
        })

    for metric, col in [
        ("Elevating grip ramp duration", "up_d1_opt"),
        ("Elevating deposit ramp duration", "up_d2_opt"),
        ("Lowering grip ramp duration", "down_d1_opt"),
        ("Lowering deposit ramp duration", "down_d2_opt"),
    ]:
        values = comparison_df[col].to_numpy(dtype=float)
        summary_rows.append({
            "metric": metric,
            "detected_mean_s": np.nan,
            "detected_sd_s": np.nan,
            "optimized_mean_s": float(np.nanmean(values)),
            "optimized_sd_s": float(np.nanstd(values, ddof=1)),
            "mean_difference_opt_minus_detected_s": np.nan,
            "mae_s": np.nan,
            "paired_t_stat": np.nan,
            "paired_t_pvalue": np.nan,
        })

    summary_df = pd.DataFrame(summary_rows)

    comparison_out = Path(ricto_dir) / "RiCTO_Timing_Comparison.csv"
    summary_out = Path(ricto_dir) / "RiCTO_Timing_Summary.csv"
    comparison_df.to_csv(comparison_out, index=False)
    summary_df.to_csv(summary_out, index=False)

    print("\n=== RiCTO timing vs loadcell threshold events ===")
    for row in summary_rows[:4]:
        print(
            f"{row['metric']}: detected {row['detected_mean_s']:.3f}±{row['detected_sd_s']:.3f} s, "
            f"optimized {row['optimized_mean_s']:.3f}±{row['optimized_sd_s']:.3f} s, "
            f"MAE {row['mae_s']:.3f} s, paired t-test p={row['paired_t_pvalue']:.4g}"
        )
    print(
        "Ramp durations (optimized): "
        f"elevating grip {summary_rows[4]['optimized_mean_s']:.3f}±{summary_rows[4]['optimized_sd_s']:.3f} s, "
        f"elevating deposit {summary_rows[5]['optimized_mean_s']:.3f}±{summary_rows[5]['optimized_sd_s']:.3f} s, "
        f"lowering grip {summary_rows[6]['optimized_mean_s']:.3f}±{summary_rows[6]['optimized_sd_s']:.3f} s, "
        f"lowering deposit {summary_rows[7]['optimized_mean_s']:.3f}±{summary_rows[7]['optimized_sd_s']:.3f} s."
    )
    print(f"Saved timing comparison: {comparison_out}")
    print(f"Saved timing summary: {summary_out}")

    return comparison_df, summary_df

#%% Lifting Analysis Setting

root_dir = r"E:\Dropbox\SEL\BOX\OpenSim\_Main_\c_AddBio_Continous"
## 조건별 데이터 입력

# 피험자 번호 입력
sub_name = 'SUB1'   # 피험자 번호 실행시 입력받고 싶다면 None으로 설정
if not sub_name:    # 피험자 번호 실행시 입력받고 싶다면 (숫자만 입력)
    input_SUB = input("<JUST TYPE ONLY THE NUMBER> \nWhich Number of SUB? : ")
    sub_name = 'SUB'+str(input_SUB)

    # 데이터 로드 위치
root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous' #SUB1\\APP1\\trial10_15_1\\JR_Results\\
APP_li = ['APP1_OneCycle', 'APP2_preRiCTO', 'APP2_postRiCTO']
kg_bpm = '15_10'
UpDown_li = ['Up', 'Down']
trial = '1'

save_dir = "E:\\Dropbox\\SEL\\BOX\\Analysis\\Symmetric\\RiCTO\\Normalized_EHF"
jr_save_dir = r"E:\Dropbox\SEL\BOX\Analysis\Symmetric\RiCTO\Normalized_JR"  # L5S1 SPM npz 저장
os.makedirs(save_dir, exist_ok=True)
os.makedirs(jr_save_dir, exist_ok=True)

# 사전에 처리해둔 Loadcell 기반 이벤트 타임포인트 로드 (스크립트와 같은 폴더의 grip_events.npz 사용)
_script_dir = Path(__file__).resolve().parent
events_dict = load_events_dict(_script_dir / "grip_events.npz")


#%% Loading JR Results

JRF = {}

for APP in APP_li:
    for UpDown in UpDown_li:
        def get_jr_path(task_idx):
            name = f"{sub_name}_{kg_bpm}_{trial}_12sec_{task_idx+1}_{APP}_JointReaction_ReactionLoads.sto"
            return os.path.join(root_dir, sub_name, APP, f"trial{kg_bpm}_{trial}", "JR_Results", name)

        save_name = f'{sub_name}_{APP}_{UpDown}'
        JRF[save_name] = normalize_JR_cropped_by_events(
            events_dict, get_jr_path, t_start_key=f"{UpDown}_grip", t_end_key=f"{UpDown}_deposit")
        # savemat(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ save_name +'.mat', locals()[save_name])
        # df = pd.DataFrame.from_dict(data=locals()[save_name], orient='columns')
        # df.to_csv(os.path.join(save_dir, save_name), '.csv')
        

## Resultant Force 데이터 저장
j1 = 'L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fx'
j2 = 'L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fy'
j3 = 'L5_S1_IVDjnt_on_lumbar5_in_lumbar5_fz'

SUB1_APP1_U_JR =        Calculate_Euclidean_Norm(JRF[f'{sub_name}_{APP_li[0]}_Up'][j1], JRF[f'{sub_name}_{APP_li[0]}_Up'][j2], JRF[f'{sub_name}_{APP_li[0]}_Up'][j3])
SUB1_APP2_pre_U_JR =    Calculate_Euclidean_Norm(JRF[f'{sub_name}_{APP_li[1]}_Up'][j1], JRF[f'{sub_name}_{APP_li[1]}_Up'][j2], JRF[f'{sub_name}_{APP_li[1]}_Up'][j3])
SUB1_APP2_post_U_JR =   Calculate_Euclidean_Norm(JRF[f'{sub_name}_{APP_li[2]}_Up'][j1], JRF[f'{sub_name}_{APP_li[2]}_Up'][j2], JRF[f'{sub_name}_{APP_li[2]}_Up'][j3])
SUB1_APP1_D_JR =        Calculate_Euclidean_Norm(JRF[f'{sub_name}_{APP_li[0]}_Down'][j1], JRF[f'{sub_name}_{APP_li[0]}_Down'][j2], JRF[f'{sub_name}_{APP_li[0]}_Down'][j3])
SUB1_APP2_pre_D_JR =    Calculate_Euclidean_Norm(JRF[f'{sub_name}_{APP_li[1]}_Down'][j1], JRF[f'{sub_name}_{APP_li[1]}_Down'][j2], JRF[f'{sub_name}_{APP_li[1]}_Down'][j3])
SUB1_APP2_post_D_JR =   Calculate_Euclidean_Norm(JRF[f'{sub_name}_{APP_li[2]}_Down'][j1], JRF[f'{sub_name}_{APP_li[2]}_Down'][j2], JRF[f'{sub_name}_{APP_li[2]}_Down'][j3])

## (reps, 101) -> (101, reps)
# L5S1_U_APP1 = pd.DataFrame(SUB1_APP1_U_JR).T
# L5S1_U_APP2 = pd.DataFrame(SUB1_APP2_pre_U_JR).T
# L5S1_U_APP4 = pd.DataFrame(SUB1_APP2_post_U_JR).T
# L5S1_D_APP1 = pd.DataFrame(SUB1_APP1_D_JR).T
# L5S1_D_APP2 = pd.DataFrame(SUB1_APP2_pre_D_JR).T
# L5S1_D_APP4 = pd.DataFrame(SUB1_APP2_post_D_JR).T


## Save Resultant Force Data to CSV
pd.DataFrame(SUB1_APP1_U_JR).to_csv(os.path.join(save_dir, f"L5S1_Resultant_{kg_bpm}_U_{APP_li[0]}.csv"))
pd.DataFrame(SUB1_APP2_pre_U_JR).to_csv(os.path.join(save_dir, f"L5S1_Resultant_{kg_bpm}_U_{APP_li[1]}.csv"))
pd.DataFrame(SUB1_APP2_post_U_JR).to_csv(os.path.join(save_dir, f"L5S1_Resultant_{kg_bpm}_U_{APP_li[2]}.csv"))
pd.DataFrame(SUB1_APP1_D_JR).to_csv(os.path.join(save_dir, f"L5S1_Resultant_{kg_bpm}_D_{APP_li[0]}.csv"))
pd.DataFrame(SUB1_APP2_pre_D_JR).to_csv(os.path.join(save_dir, f"L5S1_Resultant_{kg_bpm}_D_{APP_li[1]}.csv"))
pd.DataFrame(SUB1_APP2_post_D_JR).to_csv(os.path.join(save_dir, f"L5S1_Resultant_{kg_bpm}_D_{APP_li[2]}.csv"))


#%% EHF Analysis Setting
# EHF 결과는 locals() 대신 ehf 딕셔너리에 저장 (셀/구간만 실행해도, 실행 순서에 관계없이 안정적으로 참조 가능)
EHF = {}

APP_li = ['APP1_OneCycle', 'APP2_estimated_original', 'APP2_RiCTO-corrected']
## APP1_OneCycle EHF Analysis


for APP in APP_li:
    for UpDown in UpDown_li:
        # 클로저 보정: 루프 변수 APP를 기본인자로 고정해, 호출 시점에 항상 올바른 APP 사용
        def get_extload_path(task_idx, _app=APP):
            if _app == APP_li[0]:
                name = f"{kg_bpm}_trial{trial}_12sec_{task_idx+1}_ExtLoad{_app[0:4]}.mot"
            else:
                name = f"{kg_bpm}_trial{trial}_12sec_{task_idx+1}_ExtLoad{_app}.mot"
            return os.path.join(root_dir, sub_name, 'OneCycle_TrcMot', name)

        if APP == APP_li[0]:
            save_name = f'{sub_name}_{APP[0:4]}_{UpDown}'
        elif APP == APP_li[1]:
            save_name = f'{sub_name}_{APP[0:4]}pre_{UpDown}'
        elif APP == APP_li[2]:
            save_name = f'{sub_name}_{APP[0:4]}post_{UpDown}'
        else:
            raise ValueError(f"Invalid APP: {APP}")

        data = normalize_ExtLoad_cropped_by_events(
            events_dict, get_extload_path, t_start_key=f"{UpDown}_grip", t_end_key=f"{UpDown}_deposit", read_func=_read_mot_for_crop
        )
        Lx, Ly, Lz = 'hand_force3_vx', 'hand_force3_vy', 'hand_force3_vz'
        Rx, Ry, Rz = 'hand_force4_vx', 'hand_force4_vy', 'hand_force4_vz'
        if not data or Lx not in data:
            raise FileNotFoundError(
                f"EHF 데이터 없음: APP={APP}, UpDown={UpDown}. 경로·파일·events_dict 확인. "
                f"반환 키 샘플: {list(data.keys())[:8] if data else '빈 dict'}."
            )
        EHF[save_name] = data

        if APP == APP_li[0]:
            EHF[f'{save_name}_Lx'] = -1 * data[Lx]     # ML방향 부호 통일을 위해 x방향 왼손만 음수 처리 -> Lateral: (+), Medial: (-)
            EHF[f'{save_name}_Ly'] = data[Ly]          # Up: (+), Down: (-)
            EHF[f'{save_name}_Lz'] = -1 * data[Lz]     # AP방향 부호 반전을 위해 z방향 양손 음수 처리 -> Anterior: (+), Posterior: (-)
            EHF[f'{save_name}_Rx'] = data[Rx]
            EHF[f'{save_name}_Ry'] = data[Ry]
            EHF[f'{save_name}_Rz'] = -1 * data[Rz]     # AP방향 부호 반전을 위해 z방향 양손 음수 처리 -> Anterior: (+), Posterior: (-)
        else:
            # LOG: 기존에 EHF 뽑아낼 때 미리 부호 계산을 해버림...
            #      사실 그러면 안되는데, 일단은 빠른 제출을 위해 이곳에서 부호 변경처리를 하지 않음 (이래야 플롯 방향이 동일해지니까)
            #      제출 뒤에는, EHF를 mot로 저장하는 코드에서 부호처리하지 않고, 여기에서 다시 부호 변경처리를 해야함
            EHF[f'{save_name}_Lx'] = data[Lx]
            EHF[f'{save_name}_Ly'] = data[Ly]
            EHF[f'{save_name}_Lz'] = data[Lz]
            EHF[f'{save_name}_Rx'] = data[Rx]
            EHF[f'{save_name}_Ry'] = data[Ry]
            EHF[f'{save_name}_Rz'] = data[Rz]



#%% EHF Resultant Force Analysis

# EHF 데이터 좌우 각각 Resultant force 구해서 csv로 저장
Resultant_dir = os.path.join(save_dir,"Each_Hand","Resultant")
os.makedirs(Resultant_dir, exist_ok=True)
Save_CSV = False

# R (EHF 저장 키와 동일: SUB1_APP1_Up, SUB1_APP2pre_Up, SUB1_APP2post_Up 등)
EHF_U_APP1_R = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP1_Up_Rx'], EHF[f'{sub_name}_APP1_Up_Ry'], EHF[f'{sub_name}_APP1_Up_Rz'])
EHF_U_APP2_R = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP2pre_Up_Rx'], EHF[f'{sub_name}_APP2pre_Up_Ry'], EHF[f'{sub_name}_APP2pre_Up_Rz'])
EHF_U_APP4_R = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP2post_Up_Rx'], EHF[f'{sub_name}_APP2post_Up_Ry'], EHF[f'{sub_name}_APP2post_Up_Rz'])
EHF_D_APP1_R = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP1_Down_Rx'], EHF[f'{sub_name}_APP1_Down_Ry'], EHF[f'{sub_name}_APP1_Down_Rz'])
EHF_D_APP2_R = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP2pre_Down_Rx'], EHF[f'{sub_name}_APP2pre_Down_Ry'], EHF[f'{sub_name}_APP2pre_Down_Rz'])
EHF_D_APP4_R = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP2post_Down_Rx'], EHF[f'{sub_name}_APP2post_Down_Ry'], EHF[f'{sub_name}_APP2post_Down_Rz'])

if Save_CSV:
    pd.DataFrame(EHF_U_APP1_R).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_U_APP1_R" +".csv"))
    pd.DataFrame(EHF_U_APP2_R).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_U_APP2pre_R" +".csv"))
    pd.DataFrame(EHF_U_APP4_R).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_U_APP2post_R" +".csv"))
    pd.DataFrame(EHF_D_APP1_R).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_D_APP1_R" +".csv"))
    pd.DataFrame(EHF_D_APP2_R).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_D_APP2pre_R" +".csv"))
    pd.DataFrame(EHF_D_APP4_R).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_D_APP2post_R" +".csv"))

# L
EHF_U_APP1_L = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP1_Up_Lx'], EHF[f'{sub_name}_APP1_Up_Ly'], EHF[f'{sub_name}_APP1_Up_Lz'])
EHF_U_APP2_L = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP2pre_Up_Lx'], EHF[f'{sub_name}_APP2pre_Up_Ly'], EHF[f'{sub_name}_APP2pre_Up_Lz'])
EHF_U_APP4_L = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP2post_Up_Lx'], EHF[f'{sub_name}_APP2post_Up_Ly'], EHF[f'{sub_name}_APP2post_Up_Lz'])
EHF_D_APP1_L = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP1_Down_Lx'], EHF[f'{sub_name}_APP1_Down_Ly'], EHF[f'{sub_name}_APP1_Down_Lz'])
EHF_D_APP2_L = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP2pre_Down_Lx'], EHF[f'{sub_name}_APP2pre_Down_Ly'], EHF[f'{sub_name}_APP2pre_Down_Lz'])
EHF_D_APP4_L = Calculate_Euclidean_Norm(EHF[f'{sub_name}_APP2post_Down_Lx'], EHF[f'{sub_name}_APP2post_Down_Ly'], EHF[f'{sub_name}_APP2post_Down_Lz'])

if Save_CSV:
    pd.DataFrame(EHF_U_APP1_L).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_U_APP1_L" +".csv"))
    pd.DataFrame(EHF_U_APP2_L).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_U_APP2pre_L" +".csv"))
    pd.DataFrame(EHF_U_APP4_L).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_U_APP2post_L" +".csv"))
    pd.DataFrame(EHF_D_APP1_L).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_D_APP1_L" +".csv"))
    pd.DataFrame(EHF_D_APP2_L).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_D_APP2pre_L" +".csv"))
    pd.DataFrame(EHF_D_APP4_L).T.to_csv(os.path.join(Resultant_dir, "EHF_"+kg_bpm+"_D_APP2post_L" +".csv"))




#%% EHF RMSE Calculation (Resultant Force by Each Hand)

RMSE_dir = os.path.join(Resultant_dir,"RMSE")
os.makedirs(RMSE_dir, exist_ok=True)
Save_CSV = False

RMSE_EHF_U_APP2_R = Calculate_RMSE(EHF_U_APP1_R, EHF_U_APP2_R ,intervals)
RMSE_EHF_U_APP4_R = Calculate_RMSE(EHF_U_APP1_R, EHF_U_APP4_R ,intervals)
RMSE_EHF_D_APP2_R = Calculate_RMSE(EHF_D_APP1_R, EHF_D_APP2_R ,intervals)
RMSE_EHF_D_APP4_R = Calculate_RMSE(EHF_D_APP1_R, EHF_D_APP4_R ,intervals)

RMSE_EHF_U_APP2_L = Calculate_RMSE(EHF_U_APP1_L, EHF_U_APP2_L ,intervals)
RMSE_EHF_U_APP4_L = Calculate_RMSE(EHF_U_APP1_L, EHF_U_APP4_L ,intervals)
RMSE_EHF_D_APP2_L = Calculate_RMSE(EHF_D_APP1_L, EHF_D_APP2_L ,intervals)
RMSE_EHF_D_APP4_L = Calculate_RMSE(EHF_D_APP1_L, EHF_D_APP4_L ,intervals)

if Save_CSV:
    pd.DataFrame(RMSE_EHF_U_APP2_R).to_csv(os.path.join(RMSE_dir,'RMSE_EHF_U_APP2pre_R.csv'))
    pd.DataFrame(RMSE_EHF_U_APP4_R).to_csv(os.path.join(RMSE_dir,'RMSE_EHF_U_APP2post_R.csv'))
    pd.DataFrame(RMSE_EHF_D_APP2_R).to_csv(os.path.join(RMSE_dir,'RMSE_EHF_D_APP2pre_R.csv'))
    pd.DataFrame(RMSE_EHF_D_APP4_R).to_csv(os.path.join(RMSE_dir,'RMSE_EHF_D_APP2post_R.csv'))

    pd.DataFrame(RMSE_EHF_U_APP2_L).to_csv(os.path.join(RMSE_dir,'RMSE_EHF_U_APP2pre_L.csv'))
    pd.DataFrame(RMSE_EHF_U_APP4_L).to_csv(os.path.join(RMSE_dir,'RMSE_EHF_U_APP2post_L.csv'))
    pd.DataFrame(RMSE_EHF_D_APP2_L).to_csv(os.path.join(RMSE_dir,'RMSE_EHF_D_APP2pre_L.csv'))
    pd.DataFrame(RMSE_EHF_D_APP4_L).to_csv(os.path.join(RMSE_dir,'RMSE_EHF_D_APP2post_L.csv'))


#%% SPM Analysis - EHF Resultant Force by Each Hand
## paired t-test: abs(APP1-APP2_pre) vs abs(APP1-APP2_post)


# Absolute Error Calculation
What_to_SPM = 'L5S1'


if What_to_SPM == 'EHF':
    EHF_U_R_Diff_SPM = {'pre': abs(EHF_U_APP1_R - EHF_U_APP2_R), 'post': abs(EHF_U_APP1_R - EHF_U_APP4_R)}
    EHF_D_R_Diff_SPM = {'pre': abs(EHF_D_APP1_R - EHF_D_APP2_R), 'post': abs(EHF_D_APP1_R - EHF_D_APP4_R)}
    EHF_U_L_Diff_SPM = {'pre': abs(EHF_U_APP1_L - EHF_U_APP2_L), 'post': abs(EHF_U_APP1_L - EHF_U_APP4_L)}
    EHF_D_L_Diff_SPM = {'pre': abs(EHF_D_APP1_L - EHF_D_APP2_L), 'post': abs(EHF_D_APP1_L - EHF_D_APP4_L)}
    spm_packages = [EHF_U_R_Diff_SPM, EHF_D_R_Diff_SPM, EHF_U_L_Diff_SPM, EHF_D_L_Diff_SPM]

elif What_to_SPM == 'L5S1':
    L5S1_U_Diff_SPM = {'pre': abs(SUB1_APP1_U_JR - SUB1_APP2_pre_U_JR), 'post': abs(SUB1_APP1_U_JR - SUB1_APP2_post_U_JR)}
    L5S1_D_Diff_SPM = {'pre': abs(SUB1_APP1_D_JR - SUB1_APP2_pre_D_JR), 'post': abs(SUB1_APP1_D_JR - SUB1_APP2_post_D_JR)}
    spm_packages = [L5S1_U_Diff_SPM, L5S1_D_Diff_SPM]


for pack in range(len(spm_packages)):
    d = spm_packages[pack]
    YA = np.asarray(d['pre'], dtype=float)
    YB = np.asarray(d['post'], dtype=float)
    
    
    ###########  Exceptional Case Handling  ###########
    # spm1d: (n_subjects, n_nodes). (n_nodes, n_subjects)로 들어오면 전치.
    if YA.shape[0] > YA.shape[1]:
        YA, YB = YA.T, YB.T
    n_subj, n_nodes = YA.shape

    # Zero variance: (YA-YB)가 일부 노드에서 분산 0이면 SPM1D가 에러를 냄. 해당 열에 최소 잡음 추가.
    Y_diff = YA - YB
    var_per_node = np.var(Y_diff, axis=0)
    zero_var_nodes = np.where(var_per_node == 0)[0]
    if len(zero_var_nodes) > 0:
        np.random.seed(0)
        jitter = 1e-10 * np.random.randn(n_subj, len(zero_var_nodes))
        YA = YA.copy()
        YA[:, zero_var_nodes] += jitter
        
    #########################################################

    #(1) Conduct paired t-test:
    alpha      = 0.05
    t          = spm1d.stats.ttest_paired(YA, YB)
    ti         = t.inference(alpha, two_tailed=False, interp=True)

    #(1-1) L5S1일 때만: ti 결과를 npz로 저장 (pack 0=Elevating, 1=Lowering) → plot_l5s1.py에서 로드
    if What_to_SPM == 'L5S1':
        z_curve = np.ma.filled(ti.z, np.nan) if np.ma.is_masked(ti.z) else np.asarray(ti.z)
        Q = len(z_curve)
        scale = 100.0 / max(Q - 1, 1)
        x_pct = np.linspace(0, 100, Q)
        cluster_list = []
        for c in ti.clusters:
            ep = c.endpoints
            if hasattr(ep[0], "__len__") and not isinstance(ep[0], (int, float)):
                for seg in ep:
                    cluster_list.append((float(seg[0]) * scale, float(seg[1]) * scale))
            else:
                cluster_list.append((float(ep[0]) * scale, float(ep[1]) * scale))
        spm_label = "Elevating" if pack == 0 else "Lowering"
        np.savez(
            os.path.join(jr_save_dir, f"L5S1_SPM_{spm_label}.npz"),
            z=z_curve, zstar=float(ti.zstar), cluster_endpoints=np.array(cluster_list), alpha=alpha,
            x_pct=x_pct,
        )

        # 실행 시마다: 유의수준을 넘어서는 x축 구간을 콘솔에 2소수점으로 보고
        print(f"=== L5S1 SPM suprathreshold clusters ({spm_label}, α={alpha}) ===")
        if len(cluster_list) == 0:
            print("no suprathreshold clusters")
        else:
            for i, (a, b) in enumerate(cluster_list, 1):
                print(f"cluster {i}: {a:.2f}–{b:.2f} %")

    #(2) Plot:
    # plt.close('all')
    ### plot mean and SD:
    plt.figure( figsize=(8, 3.5) )
    ax     = plt.axes( (0.1, 0.15, 0.35, 0.8) )
    spm1d.plot.plot_mean_sd(YA, linecolor='r', facecolor='r')
    spm1d.plot.plot_mean_sd(YB, linecolor='b', facecolor='b')
    ax.axhline(y=0, color='k', linestyle=':')
    ax.set_xlabel('Time (%)')
    ax.set_ylabel('Plantar arch angle  (deg)')
    ### plot SPM results:
    ax     = plt.axes((0.55,0.15,0.35,0.8))
    ti.plot()
    ti.plot_threshold_label(fontsize=8)
    ti.plot_p_values(size=10, offsets=[(0,0.3)])
    ax.set_xlabel('Time (%)')
    ax.set_title(f'{spm_packages[pack]}')
    plt.show()


#%% RiCTO timing comparison against loadcell-threshold events
ricto_dir = r"E:\Dropbox\SEL\BOX\Analysis\Symmetric\RiCTO"
ricto_timing_df, ricto_timing_summary_df = summarize_ricto_timing_vs_loadcell(
    events_dict=events_dict,
    root_dir=root_dir,
    sub_name=sub_name,
    kg_bpm=kg_bpm,
    trial=trial,
    ricto_dir=ricto_dir,
)
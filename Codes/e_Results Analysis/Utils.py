import os; import numpy as np; import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt


def resample_data(data, resample_dim=101, flatten=False):
    """
    데이터를 처음과 끝 지점을 기준으로 자르고 resampling 하는 함수

    Args:
        data (ndarray): raw_data
        resample_dim (int): interpolate 하고싶은 정도. 보통 100(%)로 구현
        flatten (bool, optional): True일 경우 1차원으로 flatten. Defaults to False.

    Returns:
        ndarray: resampling 된 데이터
    """

    # 기존 데이터 길이와 인덱스
    data_length = len(data)
    time_index = np.arange(data_length)
    num_column = np.shape(data)[1]

    # resampling 될 데이터를 저장할 배열과 인덱스
    resampled_data = np.zeros((num_column, resample_dim))
    resampled_index = np.linspace(0, data_length-1, resample_dim)


    for i in range(0,num_column):
        interpolation_function = interp1d(time_index, data[:,i], kind='cubic')
        resampled_data[i] = interpolation_function(resampled_index)
        
    resampled_data = resampled_data.T # 행과 열 전치
    
    # flatten 옵션이 True일 경우 1차원으로 변환
    if flatten:
        resampled_data = resampled_data.flatten()

    return resampled_data


def plot_MeanStd(data, Graph=True, Label=False, color='blue', withStd=True, output=False):
    """
    numpy를 이용해 평균과 표준편차를 구한 뒤
    matplotlib.pyplot으로 평균 그래프와 표준편차 영역을 함께 보여주는 그래프를 그리고
    통계 검정을 위해 평균과 표준편차를 반환해주는 함수
    
    @ data :       1차원 데이터만 포함된 넘파이 배열 (e.g.어떤 관절의 XYZ중 한 방향의 데이터)
    @ color :      원하는 색깔, 따옴표 표시 필요함
    @ withStd :    표준편차를 평균과 함께 표시할지 아닐지에 대한 옵션
    @ output :     평균과 표준편차 반환이 필요한 경우에 함수 실행시 입력하고,
                   두 반환값을 저장할 수 있는 형식으로 표현해야 함.
    
    e.g.)   anc_mean, anc_std = ces.plot_MeanStd( test_sub2_anc_RANKLE_X, 'red', output=True )
            ------필요시-------                                                  -----------
            
    @ input : legend에 써놓을 값을 입력받도록 함
    """
    # 넘파이로 mean, std 구하기
    mean_data = np.array([])
    std_data  = np.array([])
    mean_data = np.append(mean_data, data.mean(axis=0))
    std_data  = np.append(std_data,  data.std (axis=0))
        # axis = 0 : 한 열의 모든 값을 연산, 
        #        1 : 한 행의 모든 값을 연산!
    
    if Graph != False:
        # mean 그리기
        if Label != False:
            plt.plot(mean_data, c=color, label=Label)  # legend에 써놓을 값을 입력받도록 함
        else:
            plt.plot(mean_data, c=color)
        
        # std 영역 지정 후 그리기
        if withStd == True:
            plt.fill_between(range(len(mean_data)), mean_data - std_data, mean_data + std_data,
                            alpha = 0.2, linewidth = 0, edgecolor=color, facecolor=color, antialiased=True)
            # fill_between(x, y_start, y_end,   
            #              alpha:색 투명도(max=1.0), linewidth:영역 테두리 두께,
            #              edgecolor:테두리색?, facecolor:영역 내부 색, antialiased=True:?)
    
    # 평균과 표준편차를 반환하길 원하면
    if output != False:
        return mean_data, std_data



def Normalize_IK(root_dir, sub_name, APP, kg_bpm, UpDown):
    trial_num_li = ['1', '2']
    task_num_li = list(range(1,11))

    NormIK_dict = {}
    
    for trial_num in trial_num_li:
        for task_num in task_num_li:
            file_name = kg_bpm +'_trial'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_IK.mot'
            file_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\IK_Results'+'\\'+ file_name
            
            df = pd.read_csv(file_path, sep='\t', skiprows=10)
            df.pop('time')
            df.astype(float)
            df_columns = list(df.columns)
            data = np.array(df)

            resampled_data = resample_data(data, resample_dim=101)
            
            for i in range(np.shape(resampled_data)[1]):
            
                if df_columns[i] in NormIK_dict and isinstance(NormIK_dict[df_columns[i]], np.ndarray):
                    # 기존 값 유지
                    existing_array = NormIK_dict[df_columns[i]]
                    # 새로운 배열 추가
                    combined_array = np.vstack((existing_array, resampled_data[:,i]))
                    # 딕셔너리 업데이트
                    NormIK_dict[df_columns[i]] = combined_array
                            
                else:      
                    NormIK_dict[df_columns[i]] = resampled_data[:,i]

    return NormIK_dict


def Normalize_SO(root_dir, sub_name, APP, kg_bpm, UpDown, force_or_activation):
    trial_num_li = ['1', '2']
    task_num_li = list(range(1,11))

    NormSO_dict = {}
    
    for trial_num in trial_num_li:
        for task_num in task_num_li:
            file_name = sub_name +'_'+ kg_bpm +'_'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_'+ APP +'_StaticOptimization_'+ force_or_activation +'.sto' # e.g. "SUB1_15_10_1_D1_APP1_StaticOptimization_activation.sto"
            file_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\SO_Results\\'+ file_name
            
            if force_or_activation == 'force':
                df = pd.read_csv(file_path, sep='\t', skiprows=14)
            elif force_or_activation == 'activation':
                df = pd.read_csv(file_path, sep='\t', skiprows=8)
            
            df.pop('time')
            df.astype(float)
            df_columns = list(df.columns)
            data = np.array(df)

            resampled_data = resample_data(data, resample_dim=101)
            
            for i in range(np.shape(resampled_data)[1]):
            
                if df_columns[i] in NormSO_dict and isinstance(NormSO_dict[df_columns[i]], np.ndarray):
                    # 기존 값 유지
                    existing_array = NormSO_dict[df_columns[i]]
                    # 새로운 배열 추가
                    combined_array = np.vstack((existing_array, resampled_data[:,i]))
                    # 딕셔너리 업데이트
                    NormSO_dict[df_columns[i]] = combined_array
                            
                else:      
                    NormSO_dict[df_columns[i]] = resampled_data[:,i]

    return NormSO_dict


def Normalize_JR(root_dir, sub_name, APP, kg_bpm, UpDown):
    trial_num_li = ['1', '2']
    task_num_li = list(range(1,11))

    NormJR_dict = {}
    
    for trial_num in trial_num_li:
        for task_num in task_num_li:
            file_name = sub_name +'_'+ kg_bpm +'_'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_'+ APP +'_JointReaction_ReactionLoads.sto'
            file_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results'+'\\'+ file_name
            
            df = pd.read_csv(file_path, sep='\t', skiprows=11)
            # df.pop('time')
            df.astype(float)
            df_columns = list(df.columns)
            data = np.array(df)

            resampled_data = resample_data(data, resample_dim=101)
            
            for i in range(np.shape(resampled_data)[1]):
            
                if df_columns[i] in NormJR_dict and isinstance(NormJR_dict[df_columns[i]], np.ndarray):
                    # 기존 값 유지
                    existing_array = NormJR_dict[df_columns[i]]
                    # 새로운 배열 추가
                    combined_array = np.vstack((existing_array, resampled_data[:,i]))
                    # 딕셔너리 업데이트
                    NormJR_dict[df_columns[i]] = combined_array
                            
                else:      
                    NormJR_dict[df_columns[i]] = resampled_data[:,i]

    return NormJR_dict


def Normalize_ExtLoad(root_dir, sub_name, APP, kg_bpm, UpDown):
    trial_num_li = ['1', '2']
    task_num_li = list(range(1,11))

    ExtLoad_dict = {}
    
    if APP == 'APP1' or "APP1_OneCycle" or "APP2_preRiCTO" or "APP2_postRiCTO":
        for trial_num in trial_num_li:
            for task_num in task_num_li:
                file_name = kg_bpm +'_trial'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_ExtLoad'+ APP +'.mot'
                file_path = root_dir +'\\'+ sub_name +'\\UpDown_TrcMot\\'+ file_name
                
                df = pd.read_csv(file_path, sep='\t', skiprows=6)
                # df.pop('time')
                df.astype(float)
                df_col = list(df.columns)
                df_columns = []
                for item in df_col:
                    df_columns.append(item.strip())     # 헤더 앞부분 띄어쓰기들 있으니 제거.
                data = np.array(df)
    
                resampled_data = resample_data(data, resample_dim=101)
                
                for i in range(np.shape(resampled_data)[1]):
                
                    if df_columns[i] in ExtLoad_dict and isinstance(ExtLoad_dict[df_columns[i]], np.ndarray):
                        # 기존 값 유지
                        existing_array = ExtLoad_dict[df_columns[i]]
                        # 새로운 배열 추가
                        combined_array = np.vstack((existing_array, resampled_data[:,i]))
                        # 딕셔너리 업데이트
                        ExtLoad_dict[df_columns[i]] = combined_array
                                
                    else:      
                        ExtLoad_dict[df_columns[i]] = resampled_data[:,i]
                        
    elif APP == 'APP2':
        for trial_num in trial_num_li:
            for task_num in task_num_li:
                file_name = sub_name +'_'+ kg_bpm +'_'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_'+ APP +'_BodyKinematics_acc.csv'
                file_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\BK_Results'+'\\'+ file_name
                
                df = pd.read_csv(file_path)
                # df = pd.read_csv(file_path, sep='\t', skiprows=18)
                # df.pop('time')
                df.astype(float)
                df_columns = list(df.columns)
                data = np.array(df)

                resampled_data = resample_data(data, resample_dim=101)
                
                for i in range(np.shape(resampled_data)[1]):
                
                    if df_columns[i] in ExtLoad_dict and isinstance(ExtLoad_dict[df_columns[i]], np.ndarray):
                        # 기존 값 유지
                        existing_array = ExtLoad_dict[df_columns[i]]
                        # 새로운 배열 추가
                        combined_array = np.vstack((existing_array, resampled_data[:,i]))
                        # 딕셔너리 업데이트
                        ExtLoad_dict[df_columns[i]] = combined_array
                                
                    else:      
                        ExtLoad_dict[df_columns[i]] = resampled_data[:,i]
                        
    elif APP == 'APP3' or 'APP4':
        for trial_num in trial_num_li:
            for task_num in task_num_li:
                file_name = sub_name +'_'+ kg_bpm +'_'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_'+ APP +'_JointReaction_ReactionLoads.sto'
                file_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results(ground)'+'\\'+ file_name
                
                df = pd.read_csv(file_path, sep='\t', skiprows=11)
                # df.pop('time')
                df.astype(float)
                df_columns = list(df.columns)
                data = np.array(df)

                resampled_data = resample_data(data, resample_dim=101)
                
                for i in range(np.shape(resampled_data)[1]):
                
                    if df_columns[i] in ExtLoad_dict and isinstance(ExtLoad_dict[df_columns[i]], np.ndarray):
                        # 기존 값 유지
                        existing_array = ExtLoad_dict[df_columns[i]]
                        # 새로운 배열 추가
                        combined_array = np.vstack((existing_array, resampled_data[:,i]))
                        # 딕셔너리 업데이트
                        ExtLoad_dict[df_columns[i]] = combined_array
                                
                    else:      
                        ExtLoad_dict[df_columns[i]] = resampled_data[:,i]

    return ExtLoad_dict

def normalize_JR_cropped_by_events(
    events_dict,
    get_file_path,
    t_start_key="Up_grip",
    t_end_key="Down_deposit",
    resample_dim=101,
    csv_kwargs=None,
    read_func=None,
):
    """
    이벤트 시점(Up_grip ~ Down_deposit)으로 구간을 잘라 crop_and_resample_to_pct 적용 후
    Normalize_JR와 동일한 형태의 컬럼별 딕셔너리로 반환.
    파일 경로는 get_file_path(task_idx)로 자유 설정.

    Args:
        events_dict (dict): Up_grip, Up_deposit, Down_grip, Down_deposit 키에 각각 (n_trials,) 배열.
        get_file_path (callable): get_file_path(task_idx) -> JR .sto 파일 경로 문자열.
        t_start_key: 크롭 구간 시작 시점 키 (기본 Up_grip).
        t_end_key: 크롭 구간 끝 시점 키 (기본 Down_deposit).
        resample_dim (int): 리샘플 포인트 수 (0~100%).
        csv_kwargs (dict): pd.read_csv에 넘길 인자. read_func이 None일 때만 사용. None이면 JR 기본값.
        read_func (callable): read_func(path) -> (time_arr, data_df). 지정 시 csv_kwargs 무시.

    Returns:
        dict: 컬럼명 -> (n_trials, resample_dim) ndarray.
    """
    if csv_kwargs is None:
        csv_kwargs = {"sep": "\t", "skiprows": 11}
    n_trials = len(events_dict[t_start_key])
    t_starts = events_dict[t_start_key]
    t_ends = events_dict[t_end_key]
    Norm_dict = {}
    for task_idx in range(n_trials):
        path = get_file_path(task_idx)
        if path is None or not os.path.isfile(path):
            continue
        if read_func is not None:
            time_arr, df = read_func(path)
            df = pd.DataFrame(df) if not isinstance(df, pd.DataFrame) else df
        else:
            df = pd.read_csv(path, **csv_kwargs)
            df = df.astype(float)
            time_arr = df["time"].values
        t_start, t_end = float(t_starts[task_idx]), float(t_ends[task_idx])
        if not (np.isfinite(t_start) and np.isfinite(t_end)):
            continue
        seg = crop_and_resample_to_pct(time_arr, df, t_start, t_end, resample_dim=resample_dim)
        for col, arr in seg.items():
            if col in Norm_dict:
                Norm_dict[col] = np.vstack((Norm_dict[col], arr))
            else:
                Norm_dict[col] = arr.copy().reshape(1, -1)
    return Norm_dict


def normalize_ExtLoad_cropped_by_events(
    events_dict,
    get_file_path,
    t_start_key="Up_grip",
    t_end_key="Down_deposit",
    resample_dim=101,
    csv_kwargs=None,
    read_func=None,
):
    """
    이벤트 시점으로 구간을 잘라 crop_and_resample_to_pct 적용 후
    Normalize_ExtLoad와 동일한 형태의 컬럼별 딕셔너리로 반환.
    파일 경로는 get_file_path(task_idx)로 자유 설정.

    Args:
        events_dict (dict): Up_grip, Up_deposit, Down_grip, Down_deposit 키에 각각 (n_trials,) 배열.
        get_file_path (callable): get_file_path(task_idx) -> ExtLoad .mot 파일 경로 문자열.
        t_start_key, t_end_key: 크롭 구간 시작/끝 시점 키.
        resample_dim (int): 리샘플 포인트 수.
        csv_kwargs (dict): pd.read_csv 인자. read_func이 None일 때만. None이면 .mot 기본값.
        read_func (callable): read_func(path) -> (time_arr, data_df). 지정 시 csv_kwargs 무시.

    Returns:
        dict: 컬럼명 -> (n_trials, resample_dim) ndarray.
    """
    if csv_kwargs is None:
        csv_kwargs = {"sep": "\t", "skiprows": 6}
    n_trials = len(events_dict[t_start_key])
    t_starts = events_dict[t_start_key]
    t_ends = events_dict[t_end_key]
    Norm_dict = {}
    for task_idx in range(n_trials):
        path = get_file_path(task_idx)
        if path is None or not os.path.isfile(path):
            continue
        if read_func is not None:
            time_arr, df = read_func(path)
            df = pd.DataFrame(df) if not isinstance(df, pd.DataFrame) else df
        else:
            df = pd.read_csv(path, **csv_kwargs)
            df = df.astype(float)
            if "time" not in df.columns:
                continue
            time_arr = df["time"].values
        t_start, t_end = float(t_starts[task_idx]), float(t_ends[task_idx])
        if not (np.isfinite(t_start) and np.isfinite(t_end)):
            continue
        seg = crop_and_resample_to_pct(time_arr, df, t_start, t_end, resample_dim=resample_dim)
        for col, arr in seg.items():
            if col in Norm_dict:
                Norm_dict[col] = np.vstack((Norm_dict[col], arr))
            else:
                Norm_dict[col] = arr.copy().reshape(1, -1)
    return Norm_dict


def crop_and_resample_to_pct(time_arr, data_df, t_start, t_end, resample_dim=101):
    """
    구간 [t_start, t_end]를 잘라 0~100%로 리샘플링한 뒤 컬럼별 dict로 반환.
    

    Args:
        time_arr (ndarray): 시간 벡터 (1d).
        data_df (pd.DataFrame): time 제외한 데이터 컬럼들 (또는 time 포함 시 time 컬럼 제외 후 사용).
        t_start (float): 구간 시작 시점 [s].
        t_end (float): 구간 끝 시점 [s].
        resample_dim (int): 리샘플 개수 (0~100% → 101 포인트 기본).

    Returns:
        dict: 각 컬럼명을 키로, (resample_dim,) 배열을 값으로 갖는 딕셔너리.
    """
    if "time" in data_df.columns:
        df = data_df.drop(columns=["time"])
    else:
        df = data_df.copy()
    time_arr = np.asarray(time_arr, dtype=float)
    if len(time_arr) != len(df):
        raise ValueError("time_arr and data_df must have the same length.")
    mask = (time_arr >= t_start) & (time_arr <= t_end)  # time_arr 범위 내에서 참인 것만 추출
    if not np.any(mask):
        return {c: np.full(resample_dim, np.nan) for c in df.columns}  # 범위 내 데이터 없으면 nan 채워서 반환
    segment = np.array(df.values[mask], dtype=float)
    if segment.size == 0 or segment.shape[0] < 2:
        return {c: np.full(resample_dim, np.nan) for c in df.columns}  # 데이터 없거나 부족하면 nan 채워서 반환
    resampled = resample_data(segment, resample_dim=resample_dim)
    
    return {c: resampled[:, i] for i, c in enumerate(df.columns)}  # 각 컬럼별 resampled 데이터 반환


def Calculate_RMSE(measured_df, predicted_df, intervals):
    """
    측정값과 추정값 사이의 구간별 RMSE 평균과 표준편차를 계산하는 함수.

    Parameters:
    - measured_df (pd.DataFrame): 측정된 데이터 (반복 횟수 x 시간 스텝).
    - predicted_df (pd.DataFrame): 추정된 데이터 (반복 횟수 x 시간 스텝).
    - intervals (list of tuple): 시간 구간을 나타내는 (start, end) 튜플의 리스트.

    Returns:
    - result_dict (dict): 각 구간별 RMSE 평균과 표준편차를 담은 딕셔너리.
    
    ### 사용 예시
        # 예제 데이터: 측정값과 추정값 (각각 10회 반복 측정)
        measured_df = pd.DataFrame(np.random.rand(10, n_points) * 100)  # 임의의 측정값
        predicted_df = measured_df + pd.DataFrame(np.random.randn(10, n_points) * 10)  # 임의의 추정값
        
        # # intervals 정의 에시: 4개 구간 (0-25%, 25-50%, 50-75%, 75-100%)
        # n_points = 101  # 총 시간 스텝 수 (예제)
        # intervals = [(0, n_points // 4), 
        #              (n_points // 4, n_points // 2), 
        #              (n_points // 2, 3 * n_points // 4), 
        #              (3 * n_points // 4, n_points)]

        # RMSE 계산
        rmse_results = Calculate_RMSE(measured_df, predicted_df, intervals)
        print("구간별 RMSE:", rmse_results)
    """
    result_dict = {'Interval': [], 'RMSE_Mean': [], 'RMSE_Std': []}

    for start, end in intervals:
        # 해당 구간의 데이터 추출
        measured_segment = measured_df.iloc[:, start:end].to_numpy()
        predicted_segment = predicted_df.iloc[:, start:end].to_numpy()

        # 구간별 RMSE 계산 (반복별 RMSE)
        rmse_values = np.sqrt(np.mean((measured_segment - predicted_segment) ** 2, axis=1))

        # 결과 저장
        result_dict['Interval'].append(f"{start}-{end}")
        result_dict['RMSE_Mean'].append(np.mean(rmse_values))
        result_dict['RMSE_Std'].append(np.std(rmse_values))

    return result_dict



def Crop_OneCycle(OneCycle_path, Up_path, Down_path, modified_dir=None):
    # 파일 로드
    header_OneCycle, data_OneCycle = load_sto(OneCycle_path)
    header_Up, data_Up = load_sto(Up_path)
    header_Down, data_Down = load_sto(Down_path)

    # OneCycle 파일의 time 값과 Up, Down의 time 값을 정확히 매칭
    # matched_OneCycle = data_OneCycle[data_OneCycle["time"].isin(data_Down["time"]) & data_OneCycle["time"].isin(data_Up["time"])]
    matched_Up = data_OneCycle[data_OneCycle["time"].isin(data_Up["time"])]
    matched_Down = data_OneCycle[data_OneCycle["time"].isin(data_Down["time"])]

    # Up, Down 데이터를 OneCycle 값으로 수정
    data_Up.loc[data_Up["time"].isin(data_OneCycle["time"]), :] = matched_Up.values
    data_Down.loc[data_Down["time"].isin(data_OneCycle["time"]), :] = matched_Down.values
    
    
    # 수정된 파일 저장
    if modified_dir is None:
        modified_dir = os.path.join(os.path.dirname(OneCycle_path),"Crop")
    os.makedirs(modified_dir, exist_ok=True)
    
    modified_Up_name = os.path.basename(Up_path)
    if 'APP1' in modified_Up_name:
        modified_Up_name = modified_Up_name.replace('APP1', 'APP1_Crop')
    elif 'APP2' in modified_Up_name:
        modified_Up_name = modified_Up_name.replace('APP2', 'APP2_Crop')

    modified_Down_name = os.path.basename(Down_path)
    if 'APP1' in modified_Down_name:
        modified_Down_name = modified_Down_name.replace('APP1', 'APP1_Crop')
    elif 'APP2' in modified_Down_name:
        modified_Down_name = modified_Down_name.replace('APP2', 'APP2_Crop')
    
    modified_Up_path = os.path.join(modified_dir, modified_Up_name)
    modified_Down_path = os.path.join(modified_dir, modified_Down_name)

    save_sto(modified_Up_path, header_Up, data_Up)
    save_sto(modified_Down_path, header_Down, data_Down)

    print(f"Modified files saved:\n{os.path.basename(modified_Up_path)}\n{os.path.basename(modified_Down_path)}")

# .sto 파일 로드 함수
def load_sto(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()

    # 메타데이터 분리
    header = []
    for i, line in enumerate(lines):
        if line.strip().startswith("endheader"):
            data_start_idx = i + 1
            break
        header.append(line.strip())

    # 데이터 읽기
    data = pd.read_csv(file_path, sep="\t", skiprows=data_start_idx)
    return header, data

# 수정된 .sto 파일 저장 함수
def save_sto(file_path, header, data):
    with open(file_path, "w") as file:
        file.write("\n".join(header) + "\nendheader\n")
        data.to_csv(file, sep="\t", index=False,line_terminator='\n')
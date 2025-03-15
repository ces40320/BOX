#%% 
import os; import numpy as np; import pandas as pd
import matplotlib.pyplot as plt
import csv
import bisect
from scipy.interpolate import interp1d
from scipy.signal import find_peaks
from lxml import etree

# os.chdir(r'E:\Dropbox\SEL\Python functions\OpenSim Analysis\d_Results Analysis')
# from Utils import plot_MeanStd, Normalize_IK


#%% Define Functions

def Open_TSV(filepath):
    """ tsv 기반 file 열어서 데이터 읽어온 뒤 닫는 것까지 해주는 함수 (trc, mot, sto 가능)
    
    @ filepath : 폴더에 저장된 tsv file이름 (.tsv 까지 써줘야 함)
    s"""
    with open(filepath, 'r') as f:
        reader = csv.reader(f, delimiter='\t')      # delimiter를 디폴트인 ,가 아니고 tab으로 변경
        output = [next(reader) for _ in range(5)]   # 첫 5개의 행만 읽음
    return output



def Read_TRC(filepath, start_sec= 0, end_sec= None , sampling_rate= 100):
    """ trc file을 파이썬에서 쉽게 다룰 수 있도록 수정하는 함수
    import csv ; import numpy as np ; import pandas as pd 필요
    
    @ filepath      : 폴더에 저장된 trc file이름 (.trc 까지 써줘야 함)
    @ start_sec     : 관찰하고자 하는 시작점, 단위: "초", 
                      Adaptation이 포함된 실험의 경우, 앞부분은 필요없는 것을 고려하여 설정.
    @ end_sec       : 관찰하고자 하는 끝점, 단위: "초"
    @ sampling_rate : 실험에서 설정한 카메라의 frame rate
    
    >> output : Dictionary
    output.shape => {'label_num': arr(n,), ...}
    """
    
    raw_header = Open_TSV(filepath)    # 내 함수 opentsv로 데이터 로드
    
    col_index = ['Frame','Time']    # 1,2 번째 열의 인덱스는 Frame, Time으로 고정

    for i in range(len(raw_header[4])-3):
        col_index.append(raw_header[3][(i//3)*3+2] + '_' + raw_header[4][i+2][0])   # 기존 csv파일에 있는 정보 이용해서 인덱스 list 생성
                # e.g.  (           LASI           + '_' +           X          )  => LASI_X
    
    
    new_data = pd.read_csv(filepath, sep='\t', skiprows=4)  # pandas로 원본파일 불러오기
    new_data = new_data.dropna(axis=1, how='all')           # 모든 값이 NaN인 열 삭제 <- 마지막에 \t가 입력돼있어서 비어있는 열이 생성됨...
    
    new_data.columns = col_index                            # 열 인덱스 재설정
    new_data = new_data.drop(columns='Frame')               # 열 인덱스에서 Frame 제거
    # new_data = new_data.set_index('Frame')                  # 행 인덱스 재설정
    new_data = new_data.astype(float)                       # convert all DataFrame columns (from str to float)

    
    if end_sec == None:  # 종료지점 따로 언급 없으면 데이터 끝까지 로드
        new_data = new_data[round(start_sec*sampling_rate) : len(new_data)]
    else:                   # 종료지점 지정돼있으면 그 지점까지 로드
        new_data = new_data[round(start_sec*sampling_rate) : round(end_sec*sampling_rate)]
    
    
    # DataFrame을 딕셔너리로 변환, 각 열 이름을 키로 사용
    data_dict = new_data.to_dict(orient='list')

    # value 리스트를 numpy 배열로 변환
    for key in data_dict:
        data_dict[key] = np.array(data_dict[key])

    return data_dict



def Read_GRF(filepath):
    """ mot file을 파이썬에서 쉽게 다룰 수 있도록 수정하는 함수
    import csv ; import numpy as np ; import pandas as pd 필요
    
    @ filepath      : 폴더에 저장된 mot file이름 (.mot 까지 써줘야 함)
    X start_sec     : 관찰하고자 하는 시작점, 단위: "초", 
                      Adaptation이 포함된 실험의 경우, 앞부분은 필요없는 것을 고려하여 설정.
    X end_sec       : 관찰하고자 하는 끝점, 단위: "초"
    X sampling_rate : 실험에서 설정한 카메라의 frame rate
    
    >> output : Dictionary
    output.shape => {'FP_num': arr(n,), ...}
    """
    df = pd.read_csv(filepath, sep='\t', skiprows=6)
    df.pop('time')
    df.astype(float)        
    # DataFrame을 딕셔너리로 변환, 각 열 이름을 키로 사용
    GRF_dict = df.to_dict(orient='list')
    # value 리스트를 numpy 배열로 변환
    for key in GRF_dict:
        GRF_dict[key] = np.array(GRF_dict[key])
    
    return GRF_dict



def HeelStrike_Detection(trc_path):
    '''
    Heel Strike하는 발의 순서 리스트(RL_li)와 
    Strike 시점 프레임을 넘파이 배열로(HS_arr) 출력하는 함수.
    
    output: list, ndarray
    output examples: RL_li  : ['R', 'L', 'R'] 
                     HS_arr : [708 762 817]
    
    HS Detection Algorithm: Mid_PSIS로부터 Heel마커까지의 거리가 최대인 시점.
                            FP를 밟기 직전이 감지됨.
    '''

    TRC_dict = Read_TRC(trc_path)

    ## Heel ~ midPSIS 길이 도출
    midPSIS_X = (TRC_dict['LPSI_X']+TRC_dict['RPSI_X'])/2
    midPSIS_Y = (TRC_dict['LPSI_Y']+TRC_dict['RPSI_Y'])/2
    midPSIS_Z = (TRC_dict['LPSI_Z']+TRC_dict['RPSI_Z'])/2

    midPSIS = np.vstack((midPSIS_X, midPSIS_Y, midPSIS_Z)).T

    LCAL = np.vstack((TRC_dict['LCAL_X'], TRC_dict['LCAL_Y'], TRC_dict['LCAL_Z'])).T
    RCAL = np.vstack((TRC_dict['RCAL_X'], TRC_dict['RCAL_Y'], TRC_dict['RCAL_Z'])).T

    # Left
    L_leg = midPSIS - LCAL      # LCAL에서 midPSIS까지의 벡터
    L_leg = np.square(L_leg)    # XYZ성분 제곱해서 
    L_len = L_leg[:,0]+L_leg[:,1]+L_leg[:,2]    # 합 --> 길이 도출 
    #Right
    R_leg = midPSIS - RCAL
    R_leg = np.square(R_leg)
    R_len = R_leg[:,0]+R_leg[:,1]+R_leg[:,2]

    # Save max value
    L_len_max = max(np.nan_to_num(L_len, nan=0.0))  # Replace NaN values with 0
    R_len_max = max(np.nan_to_num(R_len, nan=0.0))  # Replace NaN values with 0


    ## Heel Strike detection. 
    # Left
    L_HS, _ = find_peaks(L_len, height= 0.9 * L_len_max)     # 0.9는 일단 sub2기준 매뉴얼로 정해봄.
    # 플롯
    x = np.linspace(0, len(L_len), len(L_len))
    plt.plot(L_len)
    plt.plot(x[L_HS], L_len[L_HS],'x')
    plt.show()

    #Right
    R_HS, _ = find_peaks(R_len, height= 0.9 * R_len_max)
    # 플롯
    x = np.linspace(0, len(R_len), len(R_len))
    plt.plot(R_len)
    plt.plot(x[R_HS], R_len[R_HS],'x')
    plt.show()


    ## 데이터 크기 비교 및 HS마다의 좌우 방향 저장
    if R_HS.size > L_HS.size:   # 오른발의 HS 횟수가 더 많았다면,
        RL_li = ['R', 'L', 'R']
        HS_arr = np.hstack((R_HS[0], L_HS, R_HS[1]))
        
    else:
        RL_li = ['L', 'R', 'L']
        HS_arr = np.hstack((L_HS[0], R_HS, L_HS[1]))

    print('Initial foot strike is',RL_li[0])
    
    return RL_li, HS_arr



def Decide_FP_Area(TRC_dict, GRF_dict, HS_arr, RL_li):
    '''
    Walkway 보행 실험에서 두 발이 각각 어느 FP들을 밟았는지 할당해주는 함수.
    
    함수 Read_TRC, Read_GRF, HeelStrike_Detection의 return값을 input으로 필요로 함.
    
    output: Dictionary
    output example: {'L': [3, 4], 'R': [1, 2, 5]}
    '''
    
    # Set the position of force plates
    # Data from the images for all 5 cases, corresponding to corners (0, 1, 2, 3) and their coordinates. {{{Corner 2,3's X position is important.}}}
    FPcorners_dict = {
        'Serial': ['FP1', 'FP2', 'FP3', 'FP4', 'FP5'],
        'Corner 0 X': [0.388180, 0.794403, 1.199330, 1.606460, 2.210820],
        'Corner 0 Y': [0.011625, 0.012627, 0.013986, 0.013906, 0.017069],
        'Corner 0 Z': [0.588687, 0.588373, 0.589563, 0.590537, 0.889653],
        'Corner 1 X': [0.012209, 0.416720, 0.824492, 1.228460, 1.633430],
        'Corner 1 Y': [0.010882, 0.011442, 0.012711, 0.012832, 0.015270],
        'Corner 1 Z': [0.587860, 0.588736, 0.588574, 0.589635, 0.888540],
        'Corner 2 X': [0.011099, 0.417611, 0.822097, 1.228340, 1.634210],
        'Corner 2 Y': [0.011546, 0.012424, 0.014053, 0.013737, 0.016307],
        'Corner 2 Z': [0.011063, 0.011664, 0.012074, 0.011648, -0.288884],
        'Corner 3 X': [0.388059, 0.794990, 1.199460, 1.606340, 2.211110],
        'Corner 3 Y': [0.012280, 0.013030, 0.015086, 0.014471, 0.016922],
        'Corner 3 Z': [0.011983, 0.011593, 0.013369, 0.011525, -0.289065]
    }
    
    # Force plates의 global x좌표(AP방향) 넓찍하게 불러와서 영역의 경계 만들기
    FP_X = np.array(sorted(list(np.array(FPcorners_dict['Corner 2 X']) + 0.1) +
                           list(np.array(FPcorners_dict['Corner 3 X']) - 0.1))) # +- 0.1 m
    FP_X[0] = 0.0   # FP1의 시작점은 넓찍하지 않게 다시 원상복구 (맨끝도 하는 게 맞지만, 그 구간에서는 볼 필요가 x)
    
    # 10개 영역에 해당하는 FP들 할당
    FP_mapping = { 0: [],
    1: [1],    2: [1, 2],
    3: [2],    4: [2, 3],
    5: [3],    6: [3, 4],
    7: [4],    8: [4, 5],
    9: [5]              }
    
    # HS별로 앞발의 heel과 뒷발의 toe 마커의 x좌표를 좌우 맞춰서 불러오기
    Front_1st = TRC_dict[RL_li[0]+'CAL_X'][HS_arr[0]]
    Back_1st = TRC_dict[RL_li[1]+'tiptoe_X'][HS_arr[0]]
    Front_2nd = TRC_dict[RL_li[1]+'CAL_X'][HS_arr[1]]
    Back_2nd = TRC_dict[RL_li[2]+'tiptoe_X'][HS_arr[1]]

    # 각 마커가 어느 FP_mapping의 key가 될지 판단 
    # bisect_left()는 정렬된 FP_X 리스트에 새로운 요소를 삽입할 때 가장 왼쪽에서부터의 인덱스를 반환
    loc_Front_1st = bisect.bisect_left(FP_X, Front_1st)
    loc_Back_1st = bisect.bisect_left(FP_X, Back_1st)
    loc_Front_2nd = bisect.bisect_left(FP_X, Front_2nd)
    loc_Back_2nd = bisect.bisect_left(FP_X, Back_2nd)
    
    
    ### 좌우 발에 대한 누적 매핑 기록 저장
    FP_RL_dict = {}
    
    # 1st HS 기록... 만약 라벨링 뒤죽박죽이라 첫 HS가 FP진입 전이라면, 이 값이 []인 경우를 if문으로 짜서 지우고 한번 더 하는 식으로 코드 짜야 함
    temp_Front_1st = FP_mapping.get(loc_Front_1st, []).copy()
    temp_Back_1st = FP_mapping.get(loc_Back_1st, []).copy()
    FP_RL_dict[RL_li[0]] = temp_Front_1st
    FP_RL_dict[RL_li[1]] = temp_Back_1st

    ## 두 발에서의 중복 FP 있는지 확인 후, GRF.mot파일 불러와서 두 발 중에 하나를 결정 
    # 공통 FP가 있는지 확인
    common_FP = [item for item in FP_RL_dict['L'] if item in FP_RL_dict['R']]

    if common_FP:   # FP_RL_dict['L']과 FP_RL_dict['R'] 사이에 교집합이 있다면,
        
        # HS 직전에 VGRF가 0이 아니라면,
        if not GRF_dict[str(common_FP[0])+'_ground_force_vy'][HS_arr[0]*10] == 0.0:
            # 이 FP는 뒷발꺼 --> 앞발_dict에서 중복요소 제거
            FP_RL_dict[RL_li[0]] = [item for item in FP_RL_dict[RL_li[0]] if item not in common_FP]
            
        # HS에서 10프레임 이후 동안에도 VGRF가 0이라면,
        elif all(value == 0.0 for value in GRF_dict[str(common_FP[0]) + '_ground_force_vy'][HS_arr[0]*10:(HS_arr[0]+10)*10]):
            # 이 FP는 뒷발꺼 --> 앞발_dict에서 중복요소 제거
            FP_RL_dict[RL_li[0]] = [item for item in FP_RL_dict[RL_li[0]] if item not in common_FP]
        
        else: # HS에서 10프레임 이후 동안에 VGRF가 나타난다면,
            # COP_x 위치가 가까운 발이 이 FP 가져가기
            COP_X = GRF_dict[str(common_FP[0])+'_ground_force_px'][(HS_arr[0]+10)*10]
            # 거리 차이 계산
            distance_to_front = abs(COP_X - Front_1st)
            distance_to_back = abs(COP_X - Back_1st)
            
            if distance_to_front < distance_to_back:
                # 이 FP는 앞발꺼 --> 뒷발_dict에서 중복요소 제거
                FP_RL_dict[RL_li[1]] = [item for item in FP_RL_dict[RL_li[1]] if item not in common_FP]
                
            else:
                # 이 FP는 뒷발꺼 --> 앞발_dict에서 중복요소 제거
                FP_RL_dict[RL_li[0]] = [item for item in FP_RL_dict[RL_li[0]] if item not in common_FP]
    
    del common_FP
    
    ## 각 발에서 FP 1이 없으면 FP 2가 위치한 리스트에 1을 추가
    for key in FP_RL_dict:
        if 1 not in FP_RL_dict[key] and 2 in FP_RL_dict[key] and not any(1 in v for k, v in FP_RL_dict.items() if k != key):
            # 2의 위치를 찾아 1을 그 자리에 추가
            index_of_2 = FP_RL_dict[key].index(2)
            FP_RL_dict[key].insert(index_of_2, 1)

            
    # 2nd HS 추가기록
    temp_Front_2nd = FP_mapping.get(loc_Front_2nd, []).copy()
    temp_Back_2nd = FP_mapping.get(loc_Back_2nd, []).copy()
    FP_RL_dict[RL_li[1]].extend(temp_Front_2nd)
    FP_RL_dict[RL_li[2]].extend(temp_Back_2nd)
    
    ## 두 발에서의 중복 FP 있는지 확인 후, GRF.mot파일 불러와서 두 발 중에 하나를 결정 
    # 공통 FP가 있는지 확인
    common_FP = [item for item in FP_RL_dict['L'] if item in FP_RL_dict['R']]

    if common_FP:   # FP_RL_dict['L']과 FP_RL_dict['R'] 사이에 교집합이 있다면,
        
        # HS 직전에 VGRF가 0이 아니라면,
        if not GRF_dict[str(common_FP[0])+'_ground_force_vy'][HS_arr[1]*10] == 0.0:
            # 이 FP는 뒷발꺼 --> 앞발_dict에서 중복요소 제거
            FP_RL_dict[RL_li[1]] = [item for item in FP_RL_dict[RL_li[1]] if item not in common_FP]
            
        # HS에서 10프레임 이후 동안에도 VGRF가 0이라면,
        elif all(value == 0.0 for value in GRF_dict[str(common_FP[0]) + '_ground_force_vy'][HS_arr[1]*10:(HS_arr[1]+10)*10]):
            # 이 FP는 뒷발꺼 --> 앞발_dict에서 중복요소 제거
            FP_RL_dict[RL_li[1]] = [item for item in FP_RL_dict[RL_li[1]] if item not in common_FP]
        
        else: # HS에서 10프레임 이후 동안에 VGRF가 나타난다면,
            # COP_x 위치가 가까운 발이 이 FP 가져가기
            COP_X = GRF_dict[str(common_FP[0])+'_ground_force_px'][(HS_arr[1]+10)*10]
            # 거리 차이 계산
            distance_to_front = abs(COP_X - Front_2nd)
            distance_to_back = abs(COP_X - Back_2nd)
            
            if distance_to_front < distance_to_back:
                # 이 FP는 앞발꺼 --> 뒷발_dict에서 중복요소 제거
                FP_RL_dict[RL_li[2]] = [item for item in FP_RL_dict[RL_li[2]] if item not in common_FP]
                
            else:
                # 이 FP는 뒷발꺼 --> 앞발_dict에서 중복요소 제거
                FP_RL_dict[RL_li[1]] = [item for item in FP_RL_dict[RL_li[1]] if item not in common_FP]

    # 한 발 내에서 중복 FP 제거 후 정렬하여 리스트로 변환 (e.g., L: [1,2,2] --> L: [1,2])
    FP_RL_dict['L'] = list(sorted(set(FP_RL_dict['L'])))
    FP_RL_dict['R'] = list(sorted(set(FP_RL_dict['R'])))
    
    return FP_RL_dict



def create_GRF_SETUP_Ovg_xml(FP_RL_dict, mot_path, grf_xml_path):
    '''
    FP들을 함수 Decide_FP_Area로 할당된 발에 맞춰 xml을 생성하는 함수.
    
    참고. Decide_FP_Area: Walkway 보행 실험에서 두 발이 각각 어느 FP들을 밟았는지 할당해주는 함수.
    '''
    # XML 구조 만들기
    OpenSimDocument = etree.Element("OpenSimDocument", Version="40000")
    ExternalLoads = etree.SubElement(OpenSimDocument, "ExternalLoads", name="externalloads")
    objects = etree.SubElement(ExternalLoads, "objects")
    
    # 딕셔너리에서 데이터를 가져와서 FP_RL_dict에 맞게 태그 생성
    for side, forces in FP_RL_dict.items():
        for force in forces:
            force_side = "r" if side == 'R' else "l"
            external_force_name = f"FP{force}_{force_side}"
            
            ExternalForce = etree.SubElement(objects, "ExternalForce", name=external_force_name)
            
            # 내부 태그들 추가
            etree.SubElement(ExternalForce, "applied_to_body").text = f"calcn_{force_side}"
            etree.SubElement(ExternalForce, "force_expressed_in_body").text = "ground"
            etree.SubElement(ExternalForce, "point_expressed_in_body").text = "ground"
            etree.SubElement(ExternalForce, "force_identifier").text = f"{force}_ground_force_v"
            etree.SubElement(ExternalForce, "point_identifier").text = f"{force}_ground_force_p"
            etree.SubElement(ExternalForce, "torque_identifier").text = f"{force}_ground_torque_"
            etree.SubElement(ExternalForce, "data_source_name").text = "GRF"
    
    # <datafile> 추가
    etree.SubElement(ExternalLoads, "datafile").text = mot_path
    
    # 파일로 저장
    tree = etree.ElementTree(OpenSimDocument)
    tree.write(grf_xml_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")



#%% INPUT SETTING

root_dir = "E:\\Dropbox\\SEL\\Rajagopal_NoJC_Test"
trial_name = "None_Change_1"
trc_path = root_dir+'\\TrcMot\\'+trial_name+'.trc'
mot_path = root_dir+'\\TrcMot\\'+trial_name+'.mot'
setup_grf_path = root_dir+"\\GRF_xml\\"+ "SETUP_GRF_"+trial_name+".xml"

TRC_dict = Read_TRC(trc_path)
GRF_dict = Read_GRF(mot_path)

RL_li, HS_arr = HeelStrike_Detection(trc_path)

FP_RL_dict = Decide_FP_Area(TRC_dict, GRF_dict, HS_arr, RL_li)    
print(FP_RL_dict)

create_GRF_SETUP_Ovg_xml(FP_RL_dict, mot_path, setup_grf_path)

# %% IK Set and Run

# IK Set and Run
import opensim as osim


df = pd.read_csv(trc_path, sep='\t', skiprows=4)
trcdata = np.array(df)

base_model = r"E:\Dropbox\SEL\Rajagopal_NoJC_Test\SUB2_SMK_None_OG.osim"
model = osim.Model(os.path.join(base_model))

base_IK = "E:\Dropbox\SEL\Rajagopal_NoJC_Test\IK_Results\SETUP_IK_None_10MWT_2.xml"

IK=osim.InverseKinematicsTool(base_IK)
IK.setName('sub_name')
IK.set_marker_file(trc_path)
IK.setModel(model)
# IK.setStartTime(trcdata[1,1])
# IK.setEndTime(trcdata[-1,1])
IK.setStartTime(HS_arr[0]/100)
IK.setEndTime(HS_arr[-1]/100)
IK.setOutputMotionFileName(root_dir +'\\IK_Results'+'\\'
                            + 'IKResult_'+trial_name+'.mot')

IK.printToXML(root_dir +'\\IK_Results'+'\\'
                            + 'SETUP_IK_'+trial_name+'.xml')
IK.run()

print("IK Done:  ", trial_name)

# %% ID Set and Run

# ID Set and Run
import opensim as osim

# base_model = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ sub_name +'_Scaled_AddBiomech_'+ APP +'.osim'
base_model = r"E:\Dropbox\SEL\Rajagopal_NoJC_Test\SUB2_SMK_None_OG.osim"
model = osim.Model(os.path.join(base_model))

base_ID = r"E:\Dropbox\SEL\Rajagopal_NoJC_Test\ID_Results\SETUP_ID_None_10MWT_2.xml"

ID=osim.InverseDynamicsTool(base_ID)
ID.setName("sub_name")
ID.setModel(model)
ID.setCoordinatesFileName(root_dir+"\\IK_Results\\" + "IKResult_"+trial_name+".mot")
ID.setLowpassCutoffFrequency(6)
ID.setStartTime(HS_arr[0]/100)
ID.setEndTime(HS_arr[-1]/100)
ID.setExternalLoadsFileName(setup_grf_path)
ID.setResultsDir(root_dir+"\\ID_Results")
ID.setOutputGenForceFileName("IDResult_"+trial_name+".sto")

ID.printToXML(root_dir +'\\ID_Results\\' + 'SETUP_ID_'+trial_name+'.xml')
ID.run()

print("ID Done:  ", trial_name)
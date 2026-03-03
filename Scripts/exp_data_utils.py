import numpy as np
import pandas as pd
import opensim as osim
from scipy.signal import butter, filtfilt
import os

def euler_to_rotation_matrix(rx, ry, rz):
    """MATLAB euler_to_rotation_matrix.m과 동일한 Rz * Ry * Rx 변환"""
    rx, ry, rz = np.radians([rx, ry, rz])
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    return Rz @ (Ry @ Rx)

def apply_butterworth_filter(data, cutoff, fs, order=4):
    """4차 버터워스 저주파 필터 적용"""
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return filtfilt(b, a, data, axis=0)

def write_trc(filename, marker_data, labels, rate):
    """MATLAB writetrc.m 기능의 파이썬 구현"""
    n_frames = marker_data.shape[0]
    n_markers = len(labels)
    with open(filename, 'w') as f:
        f.write(f"PathFileType\t4\t(X/Y/Z)\t{filename}\n")
        f.write("DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames\n")
        f.write(f"{rate}\t{rate}\t{n_frames}\t{n_markers}\tm\t{rate}\t1\t{n_frames}\n")
        f.write("Frame#\tTime\t" + "\t\t\t".join(labels) + "\n")
        f.write("\t\t" + "\t".join([f"X{i+1}\tY{i+1}\tZ{i+1}" for i in range(n_markers)]) + "\n\n")
        for i in range(n_frames):
            time = i / rate
            row_data = "\t".join([f"{val:.6f}" for val in marker_data[i]])
            f.write(f"{i+1}\t{time:.6f}\t{row_data}\n")

def run_conversion(c3d_path, rb_csv_path, output_dir, trial_name):
    # 1. C3D 로드 (OpenSim API)
    adapter = osim.C3DFileAdapter()
    tables = adapter.read(c3d_path)
    
    # 마커 데이터 추출 및 49개 라벨 확인
    marker_table = adapter.getMarkersTable(tables)
    labels = list(marker_table.getColumnLabels())
    marker_rate = float(marker_table.getTableMetaDataDict().getValueForKey('DataRate').toString())
    
    # 마커 데이터 필터링 (6Hz 또는 10Hz)
    marker_np = marker_table.getMatrix().to_numpy()
    filtered_markers = apply_butterworth_filter(marker_np, 10, marker_rate)
    
    # 2. 박스(Rigid Body) CSV 로드
    rb_df = pd.read_csv(rb_csv_path, skiprows=8) # MATLAB dataLines [9, Inf] 대응
    # CSV 구조에 따라 컬럼 인덱스 확인 필요 (MATLAB 코드 기반: RotX,Y,Z, X,Y,Z 순서)
    rb_rot = rb_df.iloc[:, 2:5].values # RigidBody_0,1,2 (RotX, RotY, RotZ)
    rb_pos = rb_df.iloc[:, 5:8].values # RigidBody_3,4,5 (X, Y, Z)
    
    # 3. 힘 데이터 처리 (Force/Loadcell)
    # 이 부분은 C3D 내 ForcePlate 개수에 따라 generateMotLabels.py 로직 적용 필요
    # MATLAB 코드의 F3, F4, P3, P4 계산 로직을 여기에 구현합니다.
    
    # 4. TRC 파일 출력
    os.makedirs(output_dir, exist_ok=True)
    trc_name = os.path.join(output_dir, f"{trial_name}.trc")
    write_trc(trc_name, filtered_markers, labels, marker_rate)
    
    print(f"변환 완료: {trc_name}")

# --- 실행부 ---
if __name__ == "__main__":
    TRIAL = "15_10_trial1"
    C3D_FILE = f"path/to/{TRIAL}.c3d"
    RB_CSV = f"path/to/RigidBody_{TRIAL}.csv"
    
    run_conversion(C3D_FILE, RB_CSV, "./output", TRIAL)
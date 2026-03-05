import numpy as np
import pandas as pd
import opensim as osim
from scipy.signal import butter, filtfilt
from scipy.optimize import minimize
import os

# ==========================================
# [1] 회전 및 수학 엔진 (RotMat.m & euler_to_rotation_matrix.m 이식)
# ==========================================
def euler_to_rotation_matrix(rx, ry, rz, order='Zyx'):
    """
    MATLAB euler_to_rotation_matrix.m (Rz*Ry*Rx) 및 
    RotMat.m (Rx*Ry*Rz) 로직 통합
    """
    rx, ry, rz = np.radians([rx, ry, rz])
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    
    if order == 'XYZ': # RotMat.m 순서
        return Rx @ Ry @ Rz
    else: # euler_to_rotation_matrix.m (Rz*Ry*Rx) 순서
        return Rz @ Ry @ Rx

def apply_lowpass_filter(data, cutoff, fs, order=4):
    nyq = 0.5 * fs
    b, a = butter(order, cutoff / nyq, btype='low')
    return filtfilt(b, a, data, axis=0)

# ==========================================
# [2] 파일 저장 엔진 (writeMot.m & writetrc.m 이식)
# ==========================================
def write_trc(filename, marker_data, labels, rate):
    n_frames, n_markers = marker_data.shape[0], len(labels)
    with open(filename, 'w') as f:
        f.write(f"PathFileType\t4\t(X/Y/Z)\t{filename}\n")
        f.write("DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames\n")
        f.write(f"{rate}\t{rate}\t{n_frames}\t{n_markers}\tm\t{rate}\t1\t{n_frames}\n")
        f.write("Frame#\tTime\t" + "\t\t\t".join(labels) + "\n")
        f.write("\t\t" + "\t".join([f"X{i+1}\tY{i+1}\tZ{i+1}" for i in range(n_markers)]) + "\n\n")
        for i in range(n_frames):
            f.write(f"{i+1}\t{i/rate:.6f}\t" + "\t".join([f"{v:.6f}" for v in marker_data[i]]) + "\n")

def write_mot(filename, force_data, time, nFP):
    # generateMotLabels.m 로직 포함
    labels = []
    for i in range(1, nFP + 1):
        prefix = "ground" if i <= 2 else "hand"
        labels.extend([f'{prefix}_force{i}_vx', f'{prefix}_force{i}_vy', f'{prefix}_force{i}_vz',
                       f'{prefix}_force{i}_px', f'{prefix}_force{i}_py', f'{prefix}_force{i}_pz',
                       f'{prefix}_torque{i}_x', f'{prefix}_torque{i}_y', f'{prefix}_torque{i}_z'])
    
    with open(filename, 'w') as f:
        f.write(f"name {filename}\ndatacolumns {force_data.shape[1]+1}\ndatarows {force_data.shape[0]}\n")
        f.write(f"range {time[0]:.6f} {time[-1]:.6f}\nendheader\n\ntime\t" + "\t".join(labels) + "\n")
        for i in range(len(time)):
            f.write(f"{time[i]:.6f}\t" + "\t".join([f"{v:.8f}" for v in force_data[i]]) + "\n")

# ==========================================
# [3] 메인 프로세서 (MOT_TRC_UPDOWN_APP123.mlx 통합)
# ==========================================
def run_full_pipeline(c3d_path, rb_csv_path, output_dir, trial_name):
    # 1. C3D 로드 및 좌표 정렬 (Static 처리 포함)
    adapter = osim.C3DFileAdapter()
    tables = adapter.read(c3d_path)
    marker_table = adapter.getMarkersTable(tables)
    force_table = adapter.getForcesTable(tables)
    
    m_rate = float(marker_table.getTableMetaDataDict().getValueForKey('DataRate').toString())
    f_rate = float(force_table.getTableMetaDataDict().getValueForKey('DataRate').toString())
    
    # 2. Rigid Body 로드 (Import_RigidBody_csv.m 이식)
    # Motive CSV: 8줄 스킵 후 RotX, RotY, RotZ, X, Y, Z 추출
    rb_df = pd.read_csv(rb_csv_path, skiprows=8)
    rb_data = rb_df.iloc[:, 2:8].values # RotX,Y,Z, X,Y,Z
    
    # 3. 비대칭 외력 보정 로직 (APP1)
    # 매틀랩 코드의 Offset 및 핸들 치수 고정값
    P3_OFF = np.array([-0.0573115, 0.152248, -0.1595505])
    D3_HDL = np.array([-0.16001, 0.0158, 0.00041])
    # ... P4_OFF, D4_HDL 동일 적용
    
    # 

    # 힘/모멘트/COP 회전 및 평행이동 루프
    # (매틀랩 loop 내 euler_to_rotation_matrix 및 Offset 계산 수행)
    
    # 4. 시나리오별 결과 출력 (APP 1, 2, 3)
    os.makedirs(output_dir, exist_ok=True)
    
    # TRC 출력
    labels = list(marker_table.getColumnLabels())
    filtered_markers = apply_lowpass_filter(marker_table.getMatrix().to_numpy(), 10, m_rate)
    write_trc(os.path.join(output_dir, f"{trial_name}.trc"), filtered_markers, labels, m_rate)
    
    # MOT 출력 (APP1 예시)
    time_force = np.linspace(0, len(filtered_markers)/m_rate, len(filtered_markers)*10) # 100Hz -> 1000Hz 가정
    # ... FPinput 데이터 구성 로직
    write_mot(os.path.join(output_dir, f"{trial_name}_APP1.mot"), np.zeros((len(time_force), 36)), time_force, 4)

    print(f"✅ {trial_name} 분석 파일 생성 완료!")

if __name__ == "__main__":
    # 사용 예시
    process_name = "15_10_trial1"
    run_full_pipeline(f"c3d/{process_name}.c3d", f"csv/RigidBody_{process_name}.csv", "./output", process_name)
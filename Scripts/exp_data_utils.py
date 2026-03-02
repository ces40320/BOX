import numpy as np
import pandas as pd
import os

class ExperimentDataLoader:
    def __init__(self):
        pass

    # 1. RotMat.m & euler_to_rotation_matrix.m 통합
    @staticmethod
    def euler_to_rot_mat(ax, ay, az, order='XYZ'):
        """
        Euler 각도를 회전 행렬로 변환 (MATLAB의 RotMat/euler_to_rotation_matrix 대응)
        """
        ax, ay, az = np.radians([ax, ay, az])
        
        Rx = np.array([[1, 0, 0],
                       [0, np.cos(ax), -np.sin(ax)],
                       [0, np.sin(ax), np.cos(ax)]])
        
        Ry = np.array([[np.cos(ay), 0, np.sin(ay)],
                       [0, 1, 0],
                       [-np.sin(ay), 0, np.cos(ay)]])
        
        Rz = np.array([[np.cos(az), -np.sin(az), 0],
                       [np.sin(az), np.cos(az), 0],
                       [0, 0, 1]])
        
        # MATLAB euler_to_rotation_matrix.m 기준: Rz * Ry * Rx
        return Rz @ Ry @ Rx

    # 2. Import_RigidBody_csv.m 대응
    @staticmethod
    def import_rigid_body_csv(filename):
        """
        OptiTrack 등에서 출력된 Rigid Body CSV 데이터를 읽어옴
        """
        # 9행부터 데이터가 시작되므로 header=8 (0부터 시작)
        df = pd.read_csv(filename, skiprows=8)
        
        # MATLAB 코드의 SelectedVariableNames 및 필드 매핑 대응
        # CSV 컬럼 구조에 따라 인덱스는 조정될 수 있습니다.
        rigid_body = {
            'RotX': df.iloc[:, 2].values, # RigidBody
            'RotY': df.iloc[:, 3].values, # RigidBody_1
            'RotZ': df.iloc[:, 4].values, # RigidBody_2
            'X': df.iloc[:, 5].values,    # RigidBody_3
            'Y': df.iloc[:, 6].values,    # RigidBody_4
            'Z': df.iloc[:, 7].values     # RigidBody_5
        }
        return rigid_body

    # 3. writeMot.m & generateMotLabels.m 대응
    @staticmethod
    def write_mot(data, time, filename, n_fp=2):
        """
        OpenSim용 .mot (Motion) 파일 작성
        """
        # 라벨 생성 (generateMotLabels.m 로직)
        labels = []
        for i in range(1, n_fp + 1):
            labels.extend([f'ground_force{i}_vx', f'ground_force{i}_vy', f'ground_force{i}_vz',
                           f'ground_force{i}_px', f'ground_force{i}_py', f'ground_force{i}_pz'])
        for i in range(1, n_fp + 1):
            labels.extend([f'ground_torque{i}_x', f'ground_torque{i}_y', f'ground_torque{i}_z'])

        with open(filename, 'w') as f:
            f.write(f"name {os.path.basename(filename)}\n")
            f.write(f"datacolumns {data.shape[1] + 1}\n")
            f.write(f"datarows {len(time)}\n")
            f.write(f"range {time[0]} {time[-1]}\n")
            f.write("endheader\n\n")
            
            # Header Columns
            f.write("time\t" + "\t".join(labels) + "\n")
            
            # Data
            for t, row in zip(time, data):
                row_str = "\t".join([f"{val:.8f}" for val in row])
                f.write(f"{t:.6f}\t{row_str}\n")

    # 4. writetrc.m 대응
    @staticmethod
    def write_trc(marker_data, labels, rate, filename):
        """
        OpenSim용 .trc (Marker Trajectory) 파일 작성
        """
        n_frames = marker_data.shape[0]
        n_markers = len(labels)
        
        with open(filename, 'w') as f:
            f.write(f"PathFileType\t4\t(X/Y/Z)\t{filename}\n")
            f.write("DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames\n")
            f.write(f"{rate}\t{rate}\t{n_frames}\t{n_markers}\tm\t{rate}\t1\t{n_frames}\n")
            
            # Labels row
            header1 = "Frame#\tTime\t" + "\t\t".join(labels) + "\n"
            f.write(header1)
            
            # XYZ row
            xyz_header = "\t\t" + "\t".join([f"X{i+1}\tY{i+1}\tZ{i+1}" for i in range(n_markers)]) + "\n"
            f.write(xyz_header + "\n")
            
            # Data
            for i in range(n_frames):
                time = i / rate
                markers = "\t".join([f"{val:.6f}" for val in marker_data[i]])
                f.write(f"{i+1}\t{time:.6f}\t{markers}\n")
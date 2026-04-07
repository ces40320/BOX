import os
import sys
import shutil
import glob

import SUB_Info as _sub_info
import config_methods as _cfg

# ===== 초기 설정 --> 나중에 .yaml로 config 불러올 예정 =====
prototype = None        # If you want to output NON-official results, set any string here.
                        # e.g. "c_AddBio_Continous"
                        # Set to None for OFFICIAL results.
                                             
COWORK_ROOT_DIR = r"E:\Dropbox\SEL\BOX"     # Our Dropbox root directory (co-authors only)
# ===========================================================

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CODE_DIR)

DATA_DIR = os.path.join(COWORK_ROOT_DIR, "Experiment")

DATA_SUB_NAMECODE_li = [
    namecode
    for namecode in _sub_info.subjects.keys()
]

C3D_PATH_li = [
    glob.glob(os.path.join(DATA_DIR, namecode, "Labeled", "*.c3d"))
    for namecode in DATA_SUB_NAMECODE_li
]

RigidBody_PATH_li = [
    glob.glob(os.path.join(DATA_DIR, namecode, "RigidBody", "*.csv"))
    for namecode in DATA_SUB_NAMECODE_li
]


if prototype is not None:
    OPENSIM_DIR = os.path.join(ROOT_DIR, "OpenSim_Process", str(prototype))
    COWORK_OPENSIM_DIR = os.path.join(COWORK_ROOT_DIR, "OpenSim_Process", str(prototype))
else:
    OPENSIM_DIR = os.path.join(ROOT_DIR, "OpenSim_Process", "_Main_")
    COWORK_OPENSIM_DIR = os.path.join(COWORK_ROOT_DIR, "OpenSim_Process", "_Main_")
os.makedirs(OPENSIM_DIR, exist_ok=True)


RESULT_SUB_li = [
    f"SUB{info['SUB_number']}"
    for info in _sub_info.subjects.values()
]
for _sub_name in RESULT_SUB_li:
    os.makedirs(os.path.join(OPENSIM_DIR, _sub_name), exist_ok=True)
    _trcmot = os.path.join(OPENSIM_DIR, _sub_name, "TrcMot")
    os.makedirs(_trcmot, exist_ok=True)


# ── 피험자별 경로 헬퍼 함수 ───────────────────────────────────

def get_c3d_dir(namecode:str):
    """피험자의 C3D 파일 디렉토리"""
    return os.path.join(DATA_DIR, namecode, "Labeled")


def get_rigid_dir(namecode:str):
    """피험자의 RigidBody CSV 디렉토리"""
    return os.path.join(DATA_DIR, namecode, "RigidBody")


def get_trcmot_dir(namecode:str):
    """피험자의 TrcMot 출력 디렉토리 (없으면 생성)"""
    subject_info = _sub_info.subjects[namecode]
    sub_label = f"SUB{subject_info['SUB_number']}"  # SUB1, SUB2, ...
    protocol = subject_info["protocol"]
    dir_trcmot = os.path.join(OPENSIM_DIR, protocol, sub_label, "TrcMot")
    os.makedirs(dir_trcmot, exist_ok=True)
    return dir_trcmot

def get_APP_dir(namecode:str, app:str) -> str:
    """특정 APP의 결과 디렉토리 경로 반환.
    
    output: type(str)
        e.g. "Symmetric/SUB1/APP1"
        e.g. "Asymmetric_Triangle/SUB2/APP2"
    """
    subject_info = _sub_info.subjects[namecode]
    sub_label = f"SUB{subject_info['SUB_number']}"
    protocol = subject_info["protocol"]
    app_list = _cfg.PROTOCOL_Candidates[protocol]["APPs"]

    if app not in app_list:
        raise ValueError(f"Invalid APP {app!r} for {protocol!r} in {namecode!r}")
    
    dir_app = os.path.join(OPENSIM_DIR, protocol, sub_label, app)
    os.makedirs(dir_app, exist_ok=True)
    return dir_app


def get_all_APP_dirs(namecode:str) -> dict: 
    """해당 피험자의 모든 APP 디렉토리 경로를 dict로 반환.
    
    output: type(dict) of str
        e.g. {"APP1": "Symmetric/SUB1/APP1", "APP2": "Symmetric/SUB1/APP2", ...}
        e.g. {"APP1": "Asymmetric_Triangle/SUB2/APP1", "APP2": "Asymmetric_Triangle/SUB2/APP2", ...}
    """
    subject_info = _sub_info.subjects[namecode]
    sub_label = f"SUB{subject_info['SUB_number']}"
    protocol = subject_info["protocol"]
    app_list = _cfg.PROTOCOL_Candidates[protocol]["APPs"]

    return {
        app: os.path.join(OPENSIM_DIR, protocol, sub_label, app)
        for app in app_list
    }


def get_kgbpm_dir(namecode:str, app:str, kg_bpm:str) -> str:
    """피험자의 kg_bpm 결과 디렉토리 생성 또는 특정 kg_bpm 디렉토리 반환.
    
    output: type(str)
        e.g. "Symmetric/SUB1/APP1/15kg_10bpm_trial1"
        e.g. "Asymmetric_Triangle/SUB2/APP2/15kg_16bpm"
    """
    subject_info = _sub_info.subjects[namecode]
    sub_label = f"SUB{subject_info['SUB_number']}"  # SUB1, SUB2, ...
    protocol = subject_info["protocol"]
    dir_kgbpm = os.path.join(OPENSIM_DIR, protocol, sub_label, app, kg_bpm)
    os.makedirs(dir_kgbpm, exist_ok=True)
    return dir_kgbpm


# ── 결과 파일명 생성 헬퍼 ─────────────────────────────────────

def set_Markers_TRC_names_list(namecode):
    """피험자의 마커 TRC 파일명 리스트 생성.

    프로토콜 세그먼트 스타일에 따라 이름 생성:
      Symmetric  → SUB1_15kg_10bpm_trial1_1U.trc, ...
      ABC 스타일 → SUB2_15kg_10bpm_1AB.trc, ...
      
    output: type(list) of str
        e.g. ["SUB1_15kg_10bpm_trial1_1U.trc", "SUB1_15kg_10bpm_trial1_1D.trc", "SUB1_15kg_10bpm_trial1_2U.trc", "SUB1_15kg_10bpm_trial1_2D.trc", ...]
    """
    subject_info = _sub_info.subjects[namecode]
    sub_label = f"SUB{subject_info['SUB_number']}"  # SUB1, SUB2, ...
    protocol = subject_info["protocol"]
    segment_style = _cfg.PROTOCOL_Candidates[protocol]["segment_style"]

    filenames = []
    for kg_bpm, condition_val in subject_info["conditions"].items():
        segment_label_list = _cfg.segment_labels(condition_val["cycles"], segment_style)
        for segment_label in segment_label_list:
            filenames.append(f"{sub_label}_{kg_bpm}_{segment_label}.trc")
    return filenames


def set_ExtLoad_MOT_names_list(namecode):
    """피험자의 ExtLoad MOT 파일명 리스트 생성.

    각 세그먼트 × 각 APP 조합:
      SUB1_15kg_10bpm_trial1_1U_ExtLoadAPP1.mot, ...
      SUB2_15kg_10bpm_1AB_ExtLoadAPP1.mot, ...
      
    output: type(list) of str
        e.g. ["SUB1_15kg_10bpm_trial1_1U_ExtLoadAPP1.mot", "SUB1_15kg_10bpm_trial1_1D_ExtLoadAPP1.mot", ...]
        e.g. ["SUB2_15kg_10bpm_1AB_ExtLoadAPP1.mot", "SUB2_15kg_10bpm_1AB_ExtLoadAPP2.mot", ...]
    """
    subject_info = _sub_info.subjects[namecode]
    sub_label = f"SUB{subject_info['SUB_number']}"  # SUB1, SUB2, ...
    protocol = subject_info["protocol"]
    protocol_config = _cfg.PROTOCOL_Candidates[protocol]
    segment_style = protocol_config["segment_style"]
    app_list = protocol_config["APPs"]

    filenames = []
    for kg_bpm, condition_val in subject_info["conditions"].items():
        segment_label_list = _cfg.segment_labels(condition_val["cycles"], segment_style)
        for segment_label in segment_label_list:
            for app in app_list:
                filenames.append(f"{sub_label}_{kg_bpm}_{segment_label}_ExtLoad{app}.mot")
    return filenames


def mirror_to_cowork(src_path): 
    """OPENSIM_DIR 내 하위 폴더/파일을 COWORK_OPENSIM_DIR에도 복사"""
    if not COWORK_OPENSIM_DIR:
        return
    rel = os.path.relpath(src_path, OPENSIM_DIR)
    dst = os.path.join(COWORK_OPENSIM_DIR, rel)
    if os.path.isdir(src_path):
        shutil.copytree(src_path, dst, dirs_exist_ok=True)
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src_path, dst)
    print(f"  [CoWork] Mirrored: {dst}")
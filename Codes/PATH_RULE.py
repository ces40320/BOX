import os
import sys
import shutil
import glob

import SUB_Info as _sub_info

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
    
    TRCMOT_DIR = os.path.join(OPENSIM_DIR, _sub_name, "TrcMot")
    os.makedirs(TRCMOT_DIR, exist_ok=True)
    

# for _sub_name in RESULT_SUB_li:
#     TRC_PATH_li = [
#         f"{_sub_name}_{kg_bpm}_{cycle}_{triangle}.trc"
#         for kg_bpm in _sub_info.subjects[_sub_name]["conditions"].keys()
#         for cycle in range(1, _sub_info.subjects[_sub_name]["conditions"][kg_bpm]["cycles"] + 1)
#         for triangle in ["AB", "BC", "CA"]
#     ]
#     ExtLoad_PATH_li = [
#         f"{_sub_name}_{kg_bpm}_{cycle}_{triangle}_ExtLoad{app}.mot"
#         for kg_bpm in _sub_info.subjects[_sub_name]["conditions"].keys()
#         for cycle in range(1, _sub_info.subjects[_sub_name]["conditions"][kg_bpm]["cycles"] + 1)
#         for triangle in ["AB", "BC", "CA"]
#         for app in ["APP1", "APP2", "APP3", "APP4"]
#     ]



Current_Trc_PATH_li = [
    glob.glob(os.path.join(TRCMOT_DIR, "*.trc"))
]

Current_ExtLoad_PATH_li = [
    glob.glob(os.path.join(TRCMOT_DIR, "*.mot"))
]






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
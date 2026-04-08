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


# ── 내부 헬퍼 ─────────────────────────────────────────────────

def _sub_label(namecode: str) -> str:
    return f"SUB{_sub_info.subjects[namecode]['SUB_number']}"


def _protocol(namecode: str) -> str:
    return _sub_info.subjects[namecode]["protocol"]


# ── 입력 데이터 경로 ──────────────────────────────────────────

def get_c3d_dir(namecode: str) -> str:
    """피험자의 C3D 파일 디렉토리."""
    return os.path.join(DATA_DIR, namecode, "Labeled")


def get_rigidbody_dir(namecode: str) -> str:
    """박스의 RigidBody trajectory CSV 디렉토리."""
    return os.path.join(DATA_DIR, namecode, "RigidBody")


# ── 출력 경로 (Section 9 구조) ────────────────────────────────
#
#  OPENSIM_DIR / {protocol} / SUB{n} / {condition} / {phase} / {analysis_folder}
#
#  Symmetric  예) _Main_/Symmetric/SUB1/7kg_10bpm_trial1/Up/Markers/
#  Asymmetric 예) _Main_/Asymmetric/SUB2/7kg_10bpm/AB/ExtLoad/

def get_sub_dir(namecode: str) -> str:
    """피험자 최상위 디렉토리.

    e.g. ``_Main_/Symmetric/SUB1``
    """
    d = os.path.join(OPENSIM_DIR, _protocol(namecode), _sub_label(namecode))
    os.makedirs(d, exist_ok=True)
    return d


def get_model_dir(namecode: str) -> str:
    """모델 파일 디렉토리.

    e.g. ``…/SUB1/Model_osim``
    """
    d = os.path.join(get_sub_dir(namecode), "Model_osim")
    os.makedirs(d, exist_ok=True)
    return d


def get_condition_dir(namecode: str, condition: str) -> str:
    """조건별 디렉토리.

    e.g. ``…/SUB1/7kg_10bpm_trial1``  (Symmetric)
    e.g. ``…/SUB2/7kg_10bpm``         (Asymmetric)
    """
    d = os.path.join(get_sub_dir(namecode), condition)
    os.makedirs(d, exist_ok=True)
    return d


def get_phase_dir(namecode: str, condition: str, phase: str) -> str:
    """세그먼트 위상(방향) 디렉토리.

    e.g. ``…/7kg_10bpm_trial1/Up``   (Symmetric)
    e.g. ``…/7kg_10bpm/AB``          (Asymmetric)
    """
    d = os.path.join(get_condition_dir(namecode, condition), phase)
    os.makedirs(d, exist_ok=True)
    return d


def get_result_dir(namecode: str, condition: str, phase: str,
                   folder: str) -> str:
    """분석 단계별 결과 디렉토리 (범용).

    Parameters
    ----------
    folder : str
        ``"Markers"``, ``"ExtLoad"``, ``"IK"``, ``"IK_AddBox"``, ``"BK"``,
        ``"SO_MeasuredEHF"``, ``"JR_HeavyHand"`` 등.

    e.g. ``…/7kg_10bpm_trial1/Up/Markers``
    e.g. ``…/7kg_10bpm/AB/SO_MeasuredEHF``
    """
    d = os.path.join(get_phase_dir(namecode, condition, phase), folder)
    os.makedirs(d, exist_ok=True)
    return d


# ── 분석 단계 convenience 함수 ────────────────────────────────

def get_markers_dir(namecode: str, condition: str, phase: str) -> str:
    """``…/{condition}/{phase}/Markers``"""
    return get_result_dir(namecode, condition, phase, "Markers")


def get_extload_dir(namecode: str, condition: str, phase: str) -> str:
    """``…/{condition}/{phase}/ExtLoad``"""
    return get_result_dir(namecode, condition, phase, "ExtLoad")


def get_ik_dir(namecode: str, condition: str, phase: str,
               suffix: str = "") -> str:
    """``…/{condition}/{phase}/IK`` 또는 ``IK_AddBox`` 등.

    suffix 가 비어있으면 ``IK``, 아니면 ``IK_{suffix}``.
    """
    folder = f"IK_{suffix}" if suffix else "IK"
    return get_result_dir(namecode, condition, phase, folder)


def get_bk_dir(namecode: str, condition: str, phase: str) -> str:
    """``…/{condition}/{phase}/BK``"""
    return get_result_dir(namecode, condition, phase, "BK")


def get_so_dir(namecode: str, condition: str, phase: str,
               app: str) -> str:
    """``…/{condition}/{phase}/SO_{app}``"""
    return get_result_dir(namecode, condition, phase, f"SO_{app}")


def get_jr_dir(namecode: str, condition: str, phase: str,
               app: str) -> str:
    """``…/{condition}/{phase}/JR_{app}``"""
    return get_result_dir(namecode, condition, phase, f"JR_{app}")


# ── 복합 유틸리티 ─────────────────────────────────────────────

def build_condition_tree(namecode: str, condition: str) -> None:
    """condition 하위 전체 디렉토리 트리 일괄 생성.

    phase × (Markers, ExtLoad, IK, BK, SO_{app}, JR_{app}) 전부를 미리 만든다.
    dry-run 검증이나 파이프라인 시작 전 사전 준비에 유용.
    """
    info = _sub_info.subjects[namecode]
    pcfg = _cfg.PROTOCOL_Candidates[info["protocol"]]
    apps = pcfg["APPs"]
    for dir_name, _ in _cfg.phase_info(pcfg["segment_style"]):
        get_markers_dir(namecode, condition, dir_name)
        get_extload_dir(namecode, condition, dir_name)
        get_ik_dir(namecode, condition, dir_name)
        get_bk_dir(namecode, condition, dir_name)
        for app in apps:
            get_so_dir(namecode, condition, dir_name, app)
            get_jr_dir(namecode, condition, dir_name, app)


def seg_label_to_phase(seg_label: str, style: str) -> str:
    """세그먼트 레이블 → 위상 디렉토리명 역변환.

    ``"U3"``  → ``"Up"``  (UpDown)
    ``"AB2"`` → ``"AB"``  (ABC)
    """
    for dir_name, prefix in _cfg.phase_info(style):
        if seg_label.startswith(prefix) and seg_label[len(prefix):].isdigit():
            return dir_name
    raise ValueError(f"Cannot map {seg_label!r} to phase for style {style!r}")


def resolve_output_path(namecode: str, condition: str, seg_label: str,
                        folder: str, filename: str) -> str:
    """세그먼트 레이블 기반으로 (디렉토리 + 파일명) 절대경로를 한번에 반환.

    내부에서 seg_label → phase 자동 변환 후 get_result_dir 호출.

    >>> resolve_output_path("240124_PJH", "7kg_10bpm_trial1", "U1",
    ...     "Markers", trc_filename("240124_PJH", "7kg_10bpm_trial1", "U1"))
    '…/Symmetric/SUB1/7kg_10bpm_trial1/Up/Markers/SUB1_7kg_10bpm_trial1_U1.trc'
    """
    style = _cfg.PROTOCOL_Candidates[_protocol(namecode)]["segment_style"]
    phase = seg_label_to_phase(seg_label, style)
    return os.path.join(get_result_dir(namecode, condition, phase, folder),
                        filename)


# ── 결과 파일명 생성 헬퍼 ─────────────────────────────────────

def model_filename(namecode: str, model_type: str = "") -> str:
    """모델 .osim 파일명.

    e.g. ``SUB1_Scaled.osim``, ``SUB1_Scaled_HeavyHand.osim``
    """
    sfx = f"_{model_type}" if model_type else ""
    return f"{_sub_label(namecode)}_Scaled{sfx}.osim"



def trc_filename(namecode: str, condition: str, seg_label: str) -> str:
    """TRC 파일명.  e.g. ``SUB1_7kg_10bpm_trial1_U1.trc``"""
    return f"{_sub_label(namecode)}_{condition}_{seg_label}.trc"


def extload_mot_filename(namecode: str, condition: str,
                         seg_label: str, app: str) -> str:
    """ExtLoad MOT 파일명.  e.g. ``SUB1_7kg_10bpm_trial1_U1_ExtLoad_MeasuredEHF.mot``"""
    return f"{_sub_label(namecode)}_{condition}_{seg_label}_ExtLoad_{app}.mot"


def setup_extload_filename(condition: str, seg_label: str,
                           app: str) -> str:
    """ExtLoad SETUP XML.  e.g. ``SETUP_ExtLoad_7kg_10bpm_trial1_U1_MeasuredEHF.xml``"""
    return f"SETUP_ExtLoad_{condition}_{seg_label}_{app}.xml"


def ik_mot_filename(namecode: str, condition: str, seg_label: str,
                    suffix: str = "") -> str:
    """IK MOT 파일명.

    e.g. ``SUB1_7kg_10bpm_trial1_U1_IK.mot``
    e.g. ``SUB1_7kg_10bpm_trial1_U1_AddBox_IK.mot``
    """
    sfx = f"_{suffix}" if suffix else ""
    return f"{_sub_label(namecode)}_{condition}_{seg_label}{sfx}_IK.mot"


def setup_ik_filename(condition: str, seg_label: str,
                      suffix: str = "") -> str:
    """IK SETUP XML.  e.g. ``SETUP_IK_7kg_10bpm_trial1_U1.xml``"""
    sfx = f"_{suffix}" if suffix else ""
    return f"SETUP_IK_{condition}_{seg_label}{sfx}.xml"


def bk_sto_filename(namecode: str, condition: str, seg_label: str,
                    bk_type: str) -> str:
    """BodyKinematics STO.

    bk_type : ``"pos_global"`` | ``"vel_global"`` | ``"acc_global"``
    e.g. ``SUB1_7kg_10bpm_trial1_U1_BodyKinematics_pos_global.sto``
    """
    return (f"{_sub_label(namecode)}_{condition}_{seg_label}"
            f"_BodyKinematics_{bk_type}.sto")


def setup_bk_filename(condition: str, seg_label: str) -> str:
    """BK SETUP XML.  e.g. ``SETUP_BK_7kg_10bpm_trial1_U1.xml``"""
    return f"SETUP_BK_{condition}_{seg_label}.xml"


def so_filename(namecode: str, condition: str, seg_label: str,
                app: str, so_type: str) -> str:
    """StaticOptimization 결과.

    so_type : ``"activation"`` | ``"force"`` → ``.sto``,  ``"control"`` → ``.xml``
    e.g. ``SUB1_…_U1_MeasuredEHF_StaticOptimization_activation.sto``
    """
    ext = "xml" if so_type == "control" else "sto"
    return (f"{_sub_label(namecode)}_{condition}_{seg_label}"
            f"_{app}_StaticOptimization_{so_type}.{ext}")


def setup_so_filename(condition: str, seg_label: str, app: str) -> str:
    """SO SETUP XML.  e.g. ``SETUP_SO_7kg_10bpm_trial1_U1_MeasuredEHF.xml``"""
    return f"SETUP_SO_{condition}_{seg_label}_{app}.xml"


def jr_sto_filename(namecode: str, condition: str, seg_label: str,
                    app: str, suffix: str = "") -> str:
    """JointReaction STO.

    e.g. ``SUB1_…_U1_MeasuredEHF_JointReaction_ReactionLoads.sto``
    e.g. ``SUB1_…_U1_AddBox_JointReaction_ReactionLoads_ground.sto``
    """
    sfx = f"_{suffix}" if suffix else ""
    return (f"{_sub_label(namecode)}_{condition}_{seg_label}"
            f"_{app}_JointReaction_ReactionLoads{sfx}.sto")


def setup_jr_filename(condition: str, seg_label: str, app: str,
                      suffix: str = "") -> str:
    """JR SETUP XML.  e.g. ``SETUP_JR_7kg_10bpm_trial1_U1_MeasuredEHF.xml``"""
    sfx = f"_{suffix}" if suffix else ""
    return f"SETUP_JR_{condition}_{seg_label}_{app}{sfx}.xml"


# ── 일괄 파일명 리스트 생성 ───────────────────────────────────

def list_trc_names(namecode: str) -> list[str]:
    """피험자의 전체 TRC 파일명 리스트.

    e.g. ``["SUB1_7kg_10bpm_trial1_U1.trc", …, "SUB1_7kg_10bpm_trial1_D11.trc", …]``
    """
    info = _sub_info.subjects[namecode]
    style = _cfg.PROTOCOL_Candidates[info["protocol"]]["segment_style"]
    sub = _sub_label(namecode)
    names = []
    for cond, cval in info["conditions"].items():
        for seg in _cfg.segment_labels(cval["cycles"], style):
            names.append(f"{sub}_{cond}_{seg}.trc")
    return names


def list_extload_mot_names(namecode: str) -> list[str]:
    """피험자의 전체 ExtLoad MOT 파일명 리스트.

    e.g. ``["SUB1_7kg_10bpm_trial1_U1_ExtLoad_MeasuredEHF.mot", …]``
    """
    info = _sub_info.subjects[namecode]
    pcfg = _cfg.PROTOCOL_Candidates[info["protocol"]]
    style = pcfg["segment_style"]
    apps = pcfg["APPs"]
    sub = _sub_label(namecode)
    names = []
    for cond, cval in info["conditions"].items():
        for seg in _cfg.segment_labels(cval["cycles"], style):
            for app in apps:
                names.append(f"{sub}_{cond}_{seg}_ExtLoad_{app}.mot")
    return names


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
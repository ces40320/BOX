import os
import shutil
import glob

import SUB_Info as _sub_info
import config_methods as _cfg

# ═══════════════════════════════════════════════════════════════
#  모듈 수준 — 피험자에 의존하지 않는 상수·경로·유틸
# ═══════════════════════════════════════════════════════════════

prototype = None                                # None → "_Main_", 문자열 → 프로토타입
COWORK_ROOT_DIR = r"E:\Dropbox\SEL\BOX"

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CODE_DIR)
DATA_DIR = os.path.join(COWORK_ROOT_DIR, "Experiment")

if prototype is not None:
    OPENSIM_DIR        = os.path.join(ROOT_DIR,         "OpenSim_Process", str(prototype))
    COWORK_OPENSIM_DIR = os.path.join(COWORK_ROOT_DIR,  "OpenSim_Process", str(prototype))
else:
    OPENSIM_DIR        = os.path.join(ROOT_DIR,         "OpenSim_Process", "_Main_")
    COWORK_OPENSIM_DIR = os.path.join(COWORK_ROOT_DIR,  "OpenSim_Process", "_Main_")
os.makedirs(OPENSIM_DIR, exist_ok=True)

DATA_SUB_NAMECODE_li = list(_sub_info.subjects.keys())

C3D_PATH_li = [
    glob.glob(os.path.join(DATA_DIR, namecode, "Labeled", "*.c3d"))
    for namecode in DATA_SUB_NAMECODE_li
]
RigidBody_PATH_li = [
    glob.glob(os.path.join(DATA_DIR, namecode, "RigidBody", "*.csv"))
    for namecode in DATA_SUB_NAMECODE_li
]


def mirror_to_cowork(src_path):
    """OPENSIM_DIR 내 파일/폴더를 COWORK_OPENSIM_DIR에 복사."""
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


def _ensure_dir(*parts) -> str:
    d = os.path.join(*parts)
    os.makedirs(d, exist_ok=True)
    return d


# ═══════════════════════════════════════════════════════════════
#  ResultPaths — 피험자 단위 경로·파일명 빌더
# ═══════════════════════════════════════════════════════════════

class ResultPaths:
    """피험자(namecode) 1명에 대한 입출력 경로 및 파일명 빌더.

    ``__init__`` 에서 메타데이터를 한 번 조회하므로
    이후 호출에서 namecode 반복 불필요.

    >>> rp = ResultPaths("260306_KTH")
    >>> rp.trc_name("7kg_10bpm", "AB1")
    'SUB2_7kg_10bpm_AB1.trc'
    >>> cp = rp.for_condition("7kg_10bpm")
    >>> cp.trc_path("AB1")
    '…/Asymmetric/SUB2/7kg_10bpm/AB/Markers/SUB2_7kg_10bpm_AB1.trc'
    """

    def __init__(self, namecode: str):
        info = _sub_info.subjects[namecode]
        pcfg = _cfg.PROTOCOL_Candidates[info["protocol"]]

        self.namecode     = namecode
        self.sub_label    = f"SUB{info['SUB_number']}"
        self.protocol     = info["protocol"]
        self.conditions   = info["conditions"]
        self.style        = pcfg["segment_style"]
        self.apps         = pcfg["APPs"]
        self.segmentation = pcfg["segmentation"]

        self.c3d_dir   = os.path.join(DATA_DIR, namecode, "Labeled")
        self.rigid_dir = os.path.join(DATA_DIR, namecode, "RigidBody")
        self.sub_dir   = _ensure_dir(OPENSIM_DIR, self.protocol, self.sub_label)
        self.model_dir = _ensure_dir(self.sub_dir, "Model_osim")

    # ── 디렉토리 ─────────────────────────────────────────────

    def condition_dir(self, cond: str) -> str:
        return _ensure_dir(self.sub_dir, cond)

    def phase_dir(self, cond: str, phase: str) -> str:
        return _ensure_dir(self.sub_dir, cond, phase)

    def result_dir(self, cond: str, phase: str, folder: str) -> str:
        return _ensure_dir(self.sub_dir, cond, phase, folder)

    def markers_dir(self, cond: str, phase: str) -> str:
        return self.result_dir(cond, phase, "Markers")

    def extload_dir(self, cond: str, phase: str) -> str:
        return self.result_dir(cond, phase, "ExtLoad")

    def ik_dir(self, cond: str, phase: str, suffix: str = "") -> str:
        """e.g. ``…/Asymmetric/SUB2/7kg_10bpm/AB/IK`` (suffix 없음)
           e.g. ``…/Asymmetric/SUB2/7kg_10bpm/AB/IK_AddBox``"""
        return self.result_dir(cond, phase, f"IK_{suffix}" if suffix else "IK")

    def bk_dir(self, cond: str, phase: str) -> str:
        return self.result_dir(cond, phase, "BK")

    def so_dir(self, cond: str, phase: str, app: str) -> str:
        return self.result_dir(cond, phase, f"SO_{app}")

    def jr_dir(self, cond: str, phase: str, app: str) -> str:
        return self.result_dir(cond, phase, f"JR_{app}")

    # ── 파일명 생성 ──────────────────────────────────────────

    def model_name(self, model_type: str = "") -> str:
        """e.g. ``'SUB2_Scaled.osim'``, ``'SUB2_Scaled_HeavyHand.osim'``"""
        sfx = f"_{model_type}" if model_type else ""
        return f"{self.sub_label}_Scaled{sfx}.osim"

    def model_path(self, model_type: str = "") -> str:
        """e.g. ``…/Model_osim/SUB2_Scaled_HeavyHand.osim``"""
        return os.path.join(self.model_dir, self.model_name(model_type))

    def trc_name(self, cond: str, seg: str) -> str:
        """e.g. ``'SUB2_7kg_10bpm_AB1.trc'``"""
        return f"{self.sub_label}_{cond}_{seg}.trc"

    def extload_name(self, cond: str, seg: str, app: str) -> str:
        """e.g. ``'SUB2_7kg_10bpm_AB1_ExtLoad_MeasuredEHF.mot'``"""
        return f"{self.sub_label}_{cond}_{seg}_ExtLoad_{app}.mot"

    def setup_extload_name(self, cond: str, seg: str, app: str) -> str:
        """e.g. ``'SETUP_ExtLoad_7kg_10bpm_AB1_MeasuredEHF.xml'``"""
        return f"SETUP_ExtLoad_{cond}_{seg}_{app}.xml"

    def ik_name(self, cond: str, seg: str, suffix: str = "") -> str:
        """e.g. ``'SUB2_7kg_10bpm_AB1_IK.mot'``"""
        sfx = f"_{suffix}" if suffix else ""
        return f"{self.sub_label}_{cond}_{seg}{sfx}_IK.mot"

    def setup_ik_name(self, cond: str, seg: str, suffix: str = "") -> str:
        """e.g. ``'SETUP_IK_7kg_10bpm_AB1.xml'``"""
        sfx = f"_{suffix}" if suffix else ""
        return f"SETUP_IK_{cond}_{seg}{sfx}.xml"

    def bk_name(self, cond: str, seg: str, bk_type: str) -> str:
        """e.g. ``'SUB2_7kg_10bpm_AB1_BodyKinematics_pos_global.sto'``"""
        return f"{self.sub_label}_{cond}_{seg}_BodyKinematics_{bk_type}.sto"

    def setup_bk_name(self, cond: str, seg: str) -> str:
        """e.g. ``'SETUP_BK_7kg_10bpm_AB1.xml'``"""
        return f"SETUP_BK_{cond}_{seg}.xml"

    def so_name(self, cond: str, seg: str, app: str, so_type: str) -> str:
        """e.g. ``'SUB2_7kg_10bpm_AB1_HeavyHand_StaticOptimization_force.sto'``"""
        ext = "xml" if so_type == "control" else "sto"
        return (f"{self.sub_label}_{cond}_{seg}"
                f"_{app}_StaticOptimization_{so_type}.{ext}")

    def setup_so_name(self, cond: str, seg: str, app: str) -> str:
        """e.g. ``'SETUP_SO_7kg_10bpm_AB1_HeavyHand.xml'``"""
        return f"SETUP_SO_{cond}_{seg}_{app}.xml"

    def jr_name(self, cond: str, seg: str, app: str, suffix: str = "") -> str:
        """e.g. ``'SUB2_7kg_10bpm_AB1_PreRiCTO_JointReaction_ReactionLoads.sto'``"""
        sfx = f"_{suffix}" if suffix else ""
        return (f"{self.sub_label}_{cond}_{seg}"
                f"_{app}_JointReaction_ReactionLoads{sfx}.sto")

    def setup_jr_name(self, cond: str, seg: str, app: str,
                      suffix: str = "") -> str:
        """e.g. ``'SETUP_JR_7kg_10bpm_AB1_PreRiCTO.xml'``"""
        sfx = f"_{suffix}" if suffix else ""
        return f"SETUP_JR_{cond}_{seg}_{app}{sfx}.xml"

    # ── 유틸리티 ──────────────────────────────────────────────

    def seg_to_phase(self, seg_label: str) -> str:
        """``"AB2"`` → ``"AB"``,  ``"U3"`` → ``"Up"``"""
        for dir_name, prefix in _cfg.section_info(self.style):
            if seg_label.startswith(prefix) and seg_label[len(prefix):].isdigit():
                return dir_name
        raise ValueError(f"Cannot map {seg_label!r} for style {self.style!r}")

    def resolve(self, cond: str, seg: str, folder: str,
                filename: str) -> str:
        """seg → phase 자동 변환 후 절대경로 반환."""
        return os.path.join(
            self.result_dir(cond, self.seg_to_phase(seg), folder), filename)

    def build_condition_tree(self, cond: str) -> None:
        """condition 하위 전체 phase × analysis 디렉토리 일괄 생성."""
        for ph, _ in _cfg.section_info(self.style):
            self.markers_dir(cond, ph)
            self.extload_dir(cond, ph)
            self.ik_dir(cond, ph)
            self.bk_dir(cond, ph)
            for app in self.apps:
                self.so_dir(cond, ph, app)
                self.jr_dir(cond, ph, app)

    # ── 리스트 생성 ──────────────────────────────────────────

    def list_trc_names(self) -> list[str]:
        out = []
        for c, cv in self.conditions.items():
            for s in _cfg.section_labels(cv["cycles"], self.style):
                out.append(self.trc_name(c, s))
        return out

    def list_extload_names(self) -> list[str]:
        out = []
        for c, cv in self.conditions.items():
            for s in _cfg.section_labels(cv["cycles"], self.style):
                for a in self.apps:
                    out.append(self.extload_name(c, s, a))
        return out

    # ── ConditionPaths 팩토리 ─────────────────────────────────

    def for_condition(self, cond: str) -> "ConditionPaths":
        """condition 바인딩 하위 context 생성."""
        if cond not in self.conditions:
            raise KeyError(f"{cond!r} not in conditions of {self.namecode!r}")
        return ConditionPaths(self, cond)


# ═══════════════════════════════════════════════════════════════
#  ConditionPaths — condition 바인딩 하위 context
# ═══════════════════════════════════════════════════════════════
#
#  ResultPaths 에 위임(delegation) 하되, condition 파라미터를 고정.
#  seg_label 만 넘기면 phase 자동 추출 → 디렉토리 + 파일명 결합.
#
#  상속(IS-A) 대신 위임(HAS-A)을 택한 이유:
#    ConditionPaths 는 ResultPaths 의 "특수화"가 아니라
#    ResultPaths 의 "스코프 축소"이므로 composition 이 적합.
# ═══════════════════════════════════════════════════════════════

class ConditionPaths:
    """condition 1개에 바인딩된 경로 context.

    >>> cp = ResultPaths("260306_KTH").for_condition("7kg_10bpm")
    >>> cp.trc_path("AB1")
    '…/Asymmetric/SUB2/7kg_10bpm/AB/Markers/SUB2_7kg_10bpm_AB1.trc'
    >>> for phase, segs in cp.phase_segments().items():
    ...     for seg in segs:
    ...         print(cp.extload_path(seg, "HeavyHand"))
    """

    def __init__(self, parent: ResultPaths, cond: str):
        self._p        = parent
        self.cond      = cond
        self.cond_dir  = parent.condition_dir(cond)

        cv = parent.conditions[cond]
        self.n_cycles  = cv["cycles"]
        self.order     = cv["order"]
        self.error_log = cv.get("error_log", [])

    @property
    def sub_label(self) -> str: return self._p.sub_label
    @property
    def apps(self) -> list[str]: return self._p.apps

    # ── 위상 / 세그먼트 조회 ──────────────────────────────────

    def phase_segments(self) -> dict[str, list[str]]:
        """``{"AB": ["AB1","AB2",…], "BC": ["BC1",…], "CA": ["CA1",…]}``"""
        return _cfg.phase_segment_labels(self.n_cycles, self._p.style)

    def all_segments(self) -> list[str]:
        """``["AB1","BC1","CA1","AB2","BC2","CA2",…]``"""
        return _cfg.section_labels(self.n_cycles, self._p.style)

    def seg_to_phase(self, seg: str) -> str:
        return self._p.seg_to_phase(seg)

    # ── 디렉토리 (condition 생략) ─────────────────────────────

    def phase_dir(self, phase: str) -> str:
        """e.g. ``…/Asymmetric/SUB2/7kg_10bpm/AB``"""
        return self._p.phase_dir(self.cond, phase)

    def markers_dir(self, phase: str) -> str:
        """e.g. ``…/Asymmetric/SUB2/7kg_10bpm/AB/Markers``"""
        return self._p.markers_dir(self.cond, phase)

    def extload_dir(self, phase: str) -> str:
        """e.g. ``…/Asymmetric/SUB2/7kg_10bpm/AB/ExtLoad``"""
        return self._p.extload_dir(self.cond, phase)

    def ik_dir(self, phase: str, suffix: str = "") -> str:
        return self._p.ik_dir(self.cond, phase, suffix)

    def bk_dir(self, phase: str) -> str:
        return self._p.bk_dir(self.cond, phase)

    def so_dir(self, phase: str, app: str) -> str:
        return self._p.so_dir(self.cond, phase, app)

    def jr_dir(self, phase: str, app: str) -> str:
        return self._p.jr_dir(self.cond, phase, app)

    # ── 전체 경로 (seg → phase 자동 추출) ─────────────────────

    def trc_path(self, seg: str) -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.markers_dir(ph),
                            self._p.trc_name(self.cond, seg))

    def extload_path(self, seg: str, app: str) -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.extload_dir(ph),
                            self._p.extload_name(self.cond, seg, app))

    def setup_extload_path(self, seg: str, app: str) -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.extload_dir(ph),
                            self._p.setup_extload_name(self.cond, seg, app))

    def ik_path(self, seg: str, suffix: str = "") -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.ik_dir(ph, suffix),
                            self._p.ik_name(self.cond, seg, suffix))

    def setup_ik_path(self, seg: str, suffix: str = "") -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.ik_dir(ph, suffix),
                            self._p.setup_ik_name(self.cond, seg, suffix))

    def bk_path(self, seg: str, bk_type: str) -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.bk_dir(ph),
                            self._p.bk_name(self.cond, seg, bk_type))

    def setup_bk_path(self, seg: str) -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.bk_dir(ph),
                            self._p.setup_bk_name(self.cond, seg))

    def so_path(self, seg: str, app: str, so_type: str) -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.so_dir(ph, app),
                            self._p.so_name(self.cond, seg, app, so_type))

    def setup_so_path(self, seg: str, app: str) -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.so_dir(ph, app),
                            self._p.setup_so_name(self.cond, seg, app))

    def jr_path(self, seg: str, app: str, suffix: str = "") -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.jr_dir(ph, app),
                            self._p.jr_name(self.cond, seg, app, suffix))

    def setup_jr_path(self, seg: str, app: str, suffix: str = "") -> str:
        ph = self.seg_to_phase(seg)
        return os.path.join(self.jr_dir(ph, app),
                            self._p.setup_jr_name(self.cond, seg, app, suffix))

    # ── 일괄 ─────────────────────────────────────────────────

    def build_tree(self) -> None:
        """이 condition의 전체 디렉토리 트리 생성."""
        self._p.build_condition_tree(self.cond)

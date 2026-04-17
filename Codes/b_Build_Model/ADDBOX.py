"""OpenSim 모델에 양손 사이 박스 바디(weld/split)를 추가하는 라이브러리.

- 모듈 로드 시 하드코딩 경로 · 피험자 실행 코드 제거
- ``ADDBOXtoOSIM(...)`` 함수만 노출하고, 호출측에서
  입출력 경로 / 총 질량 / mesh dir / Constraint 여부를 파라미터로 주입
"""

import os

_OSIM_DLL_DIR = "C:/OpenSim 4.5/bin"
if hasattr(os, "add_dll_directory") and os.path.isdir(_OSIM_DLL_DIR):
    os.add_dll_directory(_OSIM_DLL_DIR)

import opensim as osim


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))

DEFAULT_MESH_DIR = os.path.join(_REPO_ROOT, "OpenSim_Process", "Model", "Design_Box")
LEFT_MESH_NAME  = "BOX_15.02kg_Half_L.STL"
RIGHT_MESH_NAME = "BOX_15.02kg_Half_R.STL"

# 15kg 박스 기준 측정값 (ASSUMPTION: 동일 형상에서 질량만 스케일)
REF_TOTAL_MASS_KG  = 15.026443611500244
REF_LEFT_MASS_KG   = 7.514212131500244
REF_RIGHT_MASS_KG  = 7.51423148

REF_LEFT_CENTER    = (0.209998,    0.113023,   0.126817)
REF_LEFT_INERTIA   = (0.0875367,   0.0686869,  0.0817151,
                      -7.5e-07,    1.13e-06,   -0.0223)

REF_RIGHT_CENTER   = (0.20999794,  0.11302869, 0.08170488)
REF_RIGHT_INERTIA  = (0.08755445,  0.06869696, 0.08172345,
                      -1.47e-06,   -1.35e-06,  0.02230830)


def _scaled_halves(box_total_mass_kg: float) -> tuple[float, float, float]:
    """총 박스 질량(kg)에서 scale 계수 및 좌/우 반 무게를 계산."""
    scale = box_total_mass_kg / REF_TOTAL_MASS_KG
    return scale, REF_LEFT_MASS_KG * scale, REF_RIGHT_MASS_KG * scale


def ADDBOXtoOSIM(
    model_path_input: str,
    model_path_output: str,
    Constraint: bool = True,
    *,
    box_total_mass_kg: float = REF_TOTAL_MASS_KG,
    mesh_dir: str | None = None,
) -> str:
    """OpenSim API로 osim 모델에 좌/우 박스 바디를 붙여 새 파일로 저장.

    Parameters
    ----------
    model_path_input : str
        입력 osim 파일 경로.
    model_path_output : str
        저장할 osim 파일 경로.
    Constraint : bool, default True
        True  → 좌·우 박스 사이에 WeldConstraint 추가 (WeldBox)
        False → 두 박스를 각자 손에만 weld-joint로 부착 (SplitBox)
    box_total_mass_kg : float
        박스 총 질량(kg). 15.02kg 기준값에서 선형 스케일로 좌/우 반 무게 및 관성 조정.
    mesh_dir : str or None
        좌/우 STL mesh가 위치한 디렉토리. None이면 ``DEFAULT_MESH_DIR`` 사용.

    Returns
    -------
    str
        생성된 osim 파일 경로(model_path_output).
    """
    mesh_dir = mesh_dir or DEFAULT_MESH_DIR
    scale, left_mass, right_mass = _scaled_halves(box_total_mass_kg)

    left_mesh_path  = os.path.join(mesh_dir, LEFT_MESH_NAME)
    right_mesh_path = os.path.join(mesh_dir, RIGHT_MESH_NAME)
    for p in (left_mesh_path, right_mesh_path):
        if not os.path.isfile(p):
            raise FileNotFoundError(f"Box mesh not found: {p}")

    os.makedirs(os.path.dirname(model_path_output), exist_ok=True)

    model = osim.Model(model_path_input)

    hand_l_body = model.getBodySet().get('hand_l')
    hand_r_body = model.getBodySet().get('hand_r')

    state = model.initSystem()
    ground = model.getGround()

    LFIN_marker = model.getMarkerSet().get('LFN2').getLocationInGround(state)
    LFIN_on_hand_l = ground.findStationLocationInAnotherFrame(state, LFIN_marker, hand_l_body)
    LFIN_Y = LFIN_on_hand_l[1]

    RFIN_marker = model.getMarkerSet().get('RFN2').getLocationInGround(state)
    RFIN_on_hand_r = ground.findStationLocationInAnotherFrame(state, RFIN_marker, hand_r_body)
    RFIN_Y = RFIN_on_hand_r[1]

    # 기존 하드코딩: LFIN_Y override. 동일 동작 유지.
    LFIN_Y = -0.09

    frame_geometry = osim.FrameGeometry()
    frame_geometry.set_display_radius(0.004)

    box_15kg_half_l_offsetframe = osim.PhysicalOffsetFrame()
    box_15kg_half_l_offsetframe.setName('box_15kg_half_l_offsetframe')
    box_15kg_half_l_offsetframe.set_translation(osim.Vec3(0.21, 0.11303, 0.20676))
    box_15kg_half_l_offsetframe.set_frame_geometry(frame_geometry)

    box_15kg_half_r_offsetframe = osim.PhysicalOffsetFrame()
    box_15kg_half_r_offsetframe.setName('box_15kg_half_r_offsetframe')
    box_15kg_half_r_offsetframe.set_translation(osim.Vec3(0.21, 0.11303, 0.001760))
    box_15kg_half_r_offsetframe.set_frame_geometry(frame_geometry)

    box_15kg_half_l_geom_1 = osim.Mesh()
    box_15kg_half_l_geom_1.set_mesh_file(left_mesh_path)
    box_15kg_half_l_geom_1.set_scale_factors(osim.Vec3(0.001, 0.001, 0.001))

    box_15kg_half_r_geom_1 = osim.Mesh()
    box_15kg_half_r_geom_1.set_mesh_file(right_mesh_path)
    box_15kg_half_r_geom_1.set_scale_factors(osim.Vec3(0.001, 0.001, 0.001))

    left_inertia  = tuple(v * scale for v in REF_LEFT_INERTIA)
    right_inertia = tuple(v * scale for v in REF_RIGHT_INERTIA)

    left_box = osim.Body()
    left_box.setName('box_15kg_half_l')
    left_box.setMass(left_mass)
    left_box.setMassCenter(osim.Vec3(*REF_LEFT_CENTER))
    left_box.setInertia(osim.Inertia(*left_inertia))
    left_box.addComponent(box_15kg_half_l_offsetframe)
    left_box.set_frame_geometry(frame_geometry)
    left_box.attachGeometry(box_15kg_half_l_geom_1)

    box_15kg_half_l_offsetframe.setParentFrame(left_box)
    model.addBody(left_box)

    right_box = osim.Body()
    right_box.setName('box_15kg_half_r')
    right_box.setMass(right_mass)
    right_box.setMassCenter(osim.Vec3(*REF_RIGHT_CENTER))
    right_box.setInertia(osim.Inertia(*right_inertia))
    right_box.addComponent(box_15kg_half_r_offsetframe)
    right_box.set_frame_geometry(frame_geometry)
    right_box.attachGeometry(box_15kg_half_r_geom_1)

    box_15kg_half_r_offsetframe.setParentFrame(right_box)
    model.addBody(right_box)

    hand_l_offset = osim.PhysicalOffsetFrame()
    hand_l_offset.setName('hand_l_offset')
    hand_l_offset.set_translation(osim.Vec3(0, RFIN_Y, 0))
    hand_l_offset.set_orientation(osim.Vec3(0, 0, 0))
    hand_l_offset.setParentFrame(hand_l_body)

    box_15kg_half_l_offset = osim.PhysicalOffsetFrame()
    box_15kg_half_l_offset.setName('box_15kg_half_l_offset')
    box_15kg_half_l_offset.set_translation(osim.Vec3(0.21, 0.1708, 0))
    box_15kg_half_l_offset.set_orientation(osim.Vec3(0, -1.5708, 0))
    box_15kg_half_l_offset.setParentFrame(left_box)

    left_bsjoint = osim.WeldJoint(
        'handle_l',
        hand_l_body, osim.Vec3(0, RFIN_Y, 0), osim.Vec3(0, 0, 0),
        left_box,    osim.Vec3(0.21, 0.1708, 0), osim.Vec3(0, -1.5708, 0),
    )
    model.addJoint(left_bsjoint)

    hand_r_offset = osim.PhysicalOffsetFrame()
    hand_r_offset.setName('hand_r_offset')
    hand_r_offset.set_translation(osim.Vec3(0, RFIN_Y, 0))
    hand_r_offset.set_orientation(osim.Vec3(0, 0, 0))
    hand_r_offset.setParentFrame(hand_r_body)

    box_15kg_half_r_offset = osim.PhysicalOffsetFrame()
    box_15kg_half_r_offset.setName('box_15kg_half_r_offset')
    box_15kg_half_r_offset.set_translation(osim.Vec3(0.21, 0.1708, 0.208570))
    box_15kg_half_r_offset.set_orientation(osim.Vec3(0, 1.5708, 0))
    box_15kg_half_r_offset.setParentFrame(right_box)

    right_bsjoint = osim.WeldJoint(
        'handle_r',
        hand_r_body, osim.Vec3(0, RFIN_Y, 0), osim.Vec3(0, 0, 0),
        right_box,   osim.Vec3(0.21, 0.1708, 0.208570), osim.Vec3(0, 1.5708, 0),
    )
    model.addJoint(right_bsjoint)

    pro_sup_l = model.getCoordinateSet().get('pro_sup_l')
    pro_sup_r = model.getCoordinateSet().get('pro_sup_r')
    pro_sup_l.setDefaultValue(1.570781)
    pro_sup_r.setDefaultValue(1.570781)

    if Constraint:
        weld_constraint = osim.WeldConstraint()
        weld_constraint.setName('WeldConstraint')
        weld_constraint.connectSocket_frame1(box_15kg_half_l_offsetframe)
        weld_constraint.connectSocket_frame2(box_15kg_half_r_offsetframe)
        model.addConstraint(weld_constraint)

    box_markers = (
        ('LTA_BOX', left_box,  (0.3496, 0.295,  0.01539)),
        ('LTP_BOX', left_box,  (0.0704, 0.295,  0.01539)),
        ('LBA_BOX', left_box,  (0.3496, 0.015, -0.01461)),
        ('LBP_BOX', left_box,  (0.0704, 0.015, -0.01461)),
        ('RTA_BOX', right_box, (0.3496, 0.295,  0.19312)),
        ('RTP_BOX', right_box, (0.0704, 0.295,  0.19312)),
        ('RBA_BOX', right_box, (0.3496, 0.015,  0.22312)),
        ('RBP_BOX', right_box, (0.0704, 0.015,  0.22312)),
    )
    for name, parent, loc in box_markers:
        m = osim.Marker()
        m.setName(name)
        m.setParentFrame(parent)
        m.set_location(osim.Vec3(*loc))
        model.addMarker(m)

    model.finalizeConnections()
    model.printToXML(model_path_output)
    return model_path_output

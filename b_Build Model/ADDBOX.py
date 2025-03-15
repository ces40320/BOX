import os
os.add_dll_directory("C:/OpenSim 4.4/bin")
# os.chdir(r'C:/OpenSim 4.4/sdk/Python')
# os.system('setup_win_python38.py')
# import numpy as np
# import pandas as pd
import opensim as osim

# 조건별 변수 입력
root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous'
sub_name = 'SUB2'
APP = 'APP3'
Constraint=True
# Constraint=False

# path 설정
input_dir  = root_dir +'\\'+ sub_name +'\\STATIC\\'+            sub_name +'_Scaled_AddBiomech.osim'
output_dir = root_dir +'\\'+ sub_name +'\\STATIC\\'+ APP +'\\'+ sub_name +'_Scaled_Weld_'+ APP +'.osim'

model_input= os.path.join(input_dir)
model_output= os.path.join(output_dir)


def ADDBOXtoOSIM(model_path_input, model_path_output, Constraint):
    """ OpenSim API를 이용해 osim 모델에서 박스를 붙이고 osim으로 새로 저장하는 함수

    INPUT
    @ model_path_input : osim파일 경로 및 파일명
    
    OUTPUT
    @ model_path_output : 새로 저장할 osim파일 경로 및 파일명 """
    
    model= osim.Model(model_path_input)

    # 모델 내 손 바디 저장(parent가 될 예정)
    hand_l_body=model.getBodySet().get('hand_l')
    hand_r_body=model.getBodySet().get('hand_r')

    state=model.initSystem()

    ground=model.getGround()

    LFIN_marker=model.getMarkerSet().get('LFN2').getLocationInGround(state)
    LFIN_marker_on_hand_l = ground.findStationLocationInAnotherFrame(state,LFIN_marker,hand_l_body)
    LFIN_Y = LFIN_marker_on_hand_l[1]
    print(LFIN_Y)

    RFIN_marker=model.getMarkerSet().get('RFN2').getLocationInGround(state)
    RFIN_marker_on_hand_r = ground.findStationLocationInAnotherFrame(state,RFIN_marker,hand_r_body)
    RFIN_Y = RFIN_marker_on_hand_r[1]
    print(RFIN_Y)

    LFIN_Y = -0.09

    frame_geometry=osim.FrameGeometry()
    frame_geometry.set_display_radius(0.004)

    # L
    box_15kg_half_l_offsetframe=osim.PhysicalOffsetFrame()
    box_15kg_half_l_offsetframe.setName('box_15kg_half_l_offsetframe')
    box_15kg_half_l_offsetframe.set_translation(osim.Vec3(0.21, 0.11303, 0.20676))
    box_15kg_half_l_offsetframe.set_frame_geometry(frame_geometry)
    # R
    box_15kg_half_r_offsetframe=osim.PhysicalOffsetFrame()
    box_15kg_half_r_offsetframe.setName('box_15kg_half_r_offsetframe')
    box_15kg_half_r_offsetframe.set_translation(osim.Vec3(0.21, 0.11303, 0.001760))
    box_15kg_half_r_offsetframe.set_frame_geometry(frame_geometry)

    # L
    box_15kg_half_l_geom_1=osim.Mesh()
    box_15kg_half_l_geom_1.set_mesh_file("E:\Dropbox\Sanjabu\Analysis\Model\Design_Box\BOX_15.02kg_Half_L.STL")
    box_15kg_half_l_geom_1.set_scale_factors(osim.Vec3(0.001,0.001,0.001))
    # R
    box_15kg_half_r_geom_1=osim.Mesh()
    box_15kg_half_r_geom_1.set_mesh_file("E:\Dropbox\Sanjabu\Analysis\Model\Design_Box\BOX_15.02kg_Half_R.STL")
    box_15kg_half_r_geom_1.set_scale_factors(osim.Vec3(0.001,0.001,0.001))


    left_box=osim.Body()
    left_box.setName('box_15kg_half_l')
    left_box.setMass(7.514212131500244)
    left_box.setMassCenter(osim.Vec3(0.209998, 0.113023, 0.126817))
    left_box.setInertia(osim.Inertia(0.0875367, 0.0686869, 0.0817151, -7.5e-07, 1.13e-06, -0.0223))
    left_box.addComponent(box_15kg_half_l_offsetframe)
    left_box.set_frame_geometry(frame_geometry)
    left_box.attachGeometry(box_15kg_half_l_geom_1)

    box_15kg_half_l_offsetframe.setParentFrame(left_box)
    model.addBody(left_box)

    right_box=osim.Body()
    right_box.setName('box_15kg_half_r')
    right_box.setMass(7.51423148)
    right_box.setMassCenter(osim.Vec3(0.20999794, 0.11302869, 0.08170488))
    right_box.setInertia(osim.Inertia(0.08755445, 0.06869696, 0.08172345, -0.00000147, -0.00000135, 0.02230830))
    right_box.addComponent(box_15kg_half_r_offsetframe)
    right_box.set_frame_geometry(frame_geometry)
    right_box.attachGeometry(box_15kg_half_r_geom_1)

    box_15kg_half_r_offsetframe.setParentFrame(right_box)
    model.addBody(right_box)




    hand_l_offset=osim.PhysicalOffsetFrame()
    hand_l_offset.setName('hand_l_offset')
    hand_l_offset.set_translation(osim.Vec3(0, RFIN_Y, 0))  # 이 수치는 FIN y좌표
    hand_l_offset.set_orientation(osim.Vec3(0,0,0))
    hand_l_offset.setParentFrame(hand_l_body)

    box_15kg_half_l_offset=osim.PhysicalOffsetFrame()
    box_15kg_half_l_offset.setName('box_15kg_half_l_offset')
    box_15kg_half_l_offset.set_translation(osim.Vec3(0.21, 0.1708, 0))
    box_15kg_half_l_offset.set_orientation(osim.Vec3(0, -1.5708, 0))
    box_15kg_half_l_offset.setParentFrame(left_box)

    locationInParent_l    = osim.Vec3(0, RFIN_Y, 0)  # 이 수치는 FIN y좌표
    orientationInParent_l = osim.Vec3(0,0,0)
    locationInChild_l     = osim.Vec3(0.21, 0.1708, 0)
    orientationInChild_l  = osim.Vec3(0, -1.5708, 0)
    left_bsjoint = osim.WeldJoint('handle_l', hand_l_body, locationInParent_l, orientationInParent_l,
                                    left_box, locationInChild_l, orientationInChild_l)

    model.addJoint(left_bsjoint)


    hand_r_offset=osim.PhysicalOffsetFrame()
    hand_r_offset.setName('hand_r_offset')
    hand_r_offset.set_translation(osim.Vec3(0, RFIN_Y, 0))  # 이 수치는 RFIN y좌표
    hand_r_offset.set_orientation(osim.Vec3(0,0,0))
    hand_r_offset.setParentFrame(hand_r_body)

    box_15kg_half_r_offset=osim.PhysicalOffsetFrame()
    box_15kg_half_r_offset.setName('box_15kg_half_r_offset')
    box_15kg_half_r_offset.set_translation(osim.Vec3(0.21, 0.1708, 0.208570))
    box_15kg_half_r_offset.set_orientation(osim.Vec3(0, 1.5708, 0)) # radian value (1.5708 == pi/2)
    box_15kg_half_r_offset.setParentFrame(right_box)

    locationInParent_r    = osim.Vec3(0, RFIN_Y, 0)  # 이 수치는 RFIN y좌표
    orientationInParent_r = osim.Vec3(0,0,0)
    locationInChild_r     = osim.Vec3(0.21, 0.1708, 0.208570)
    orientationInChild_r  = osim.Vec3(0, 1.5708, 0) # radian value (1.5708 == pi/2)
    right_bsjoint = osim.WeldJoint('handle_r', hand_r_body, locationInParent_r, orientationInParent_r,
                                    right_box, locationInChild_r, orientationInChild_r)

    model.addJoint(right_bsjoint)



    pro_sup_l = model.getCoordinateSet().get('pro_sup_l')
    pro_sup_r = model.getCoordinateSet().get('pro_sup_r')
    pro_sup_l.setDefaultValue(1.570781) # 90도 회전
    pro_sup_r.setDefaultValue(1.570781)


    if Constraint == True:
        weld_constraint = osim.WeldConstraint()
        weld_constraint.setName('WeldConstraint')
        weld_constraint.connectSocket_frame1(box_15kg_half_l_offsetframe)
        weld_constraint.connectSocket_frame2(box_15kg_half_r_offsetframe)
        model.addConstraint(weld_constraint)
        # point_constraint = osim.PointConstraint()
        # point_constraint.setName('PointConstraint')
        # point_constraint.connectSocket_body_1(box_15kg_half_l_offsetframe)
        # point_constraint.connectSocket_body_2(box_15kg_half_r_offsetframe)
        # model.addConstraint(point_constraint)



    LTA_BOX=osim.Marker()
    LTA_BOX.setName('LTA_BOX')
    LTA_BOX.setParentFrame(left_box)
    LTA_BOX.set_location(osim.Vec3(0.3496, 0.295, 0.01539))
    model.addMarker(LTA_BOX)

    LTP_BOX=osim.Marker()
    LTP_BOX.setName('LTP_BOX')
    LTP_BOX.setParentFrame(left_box)
    LTP_BOX.set_location(osim.Vec3(0.0704, 0.295, 0.01539))
    model.addMarker(LTP_BOX)

    LBA_BOX=osim.Marker()
    LBA_BOX.setName('LBA_BOX')
    LBA_BOX.setParentFrame(left_box)
    LBA_BOX.set_location(osim.Vec3(0.3496, 0.015, -0.01461))
    model.addMarker(LBA_BOX)

    LBP_BOX=osim.Marker()
    LBP_BOX.setName('LBP_BOX')
    LBP_BOX.setParentFrame(left_box)
    LBP_BOX.set_location(osim.Vec3(0.0704, 0.015, -0.01461))
    model.addMarker(LBP_BOX)

    RTA_BOX=osim.Marker()
    RTA_BOX.setName('RTA_BOX')
    RTA_BOX.setParentFrame(right_box)
    RTA_BOX.set_location(osim.Vec3(0.3496, 0.295, 0.19312))
    model.addMarker(RTA_BOX)

    RTP_BOX=osim.Marker()
    RTP_BOX.setName('RTP_BOX')
    RTP_BOX.setParentFrame(right_box)
    RTP_BOX.set_location(osim.Vec3(0.0704, 0.295, 0.19312))
    model.addMarker(RTP_BOX)

    RBA_BOX=osim.Marker()
    RBA_BOX.setName('RBA_BOX')
    RBA_BOX.setParentFrame(right_box)
    RBA_BOX.set_location(osim.Vec3(0.3496, 0.015, 0.22312))
    model.addMarker(RBA_BOX)

    RBP_BOX=osim.Marker()
    RBP_BOX.setName('RBP_BOX')
    RBP_BOX.setParentFrame(right_box)
    RBP_BOX.set_location(osim.Vec3(0.0704, 0.015, 0.22312))
    model.addMarker(RBP_BOX)

    model.finalizeConnections()
    model.printToXML(model_path_output)
    

# 함수 실행
ADDBOXtoOSIM(model_input, model_output, Constraint)
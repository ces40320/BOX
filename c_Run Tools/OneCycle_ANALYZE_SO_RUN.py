import os
os.add_dll_directory("C:/OpenSim 4.4/bin")
# import numpy as np
# import pandas as pd
import opensim as osim
import time



def OneCycle_SO_RUN(root_dir, sub_name, APP, kg_bpm, trial_num, task_num):
    model_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ sub_name +'_Scaled_AddBiomech_'+ APP[0:4] +'.osim'
    model = osim.Model(model_path)
    
    
    def add_reserve(model, coord, max_control):
        actu = osim.CoordinateActuator(coord)
        if coord.startswith('lumbar'):
            prefix = 'torque_'
        elif coord.startswith('pelvis'):
            prefix = 'residual_'
        else:
            prefix = 'reserve_'
        actu.setName(prefix + coord)
        actu.setMinControl(-10000)
        actu.setMaxControl(10000)
        actu.setOptimalForce(max_control)
        model.addForce(actu)


    add_reserve(model, 'pelvis_tx', 100)
    add_reserve(model, 'pelvis_ty', 200)
    add_reserve(model, 'pelvis_tz', 100)
    
    add_reserve(model, 'pelvis_tilt', 80)
    add_reserve(model, 'pelvis_list', 80)
    add_reserve(model, 'pelvis_rotation', 80)
    
    add_reserve(model,'L5_S1_Flex_Ext',10)
    add_reserve(model,'L5_S1_Lat_Bending',5)
    add_reserve(model,'L5_S1_axial_rotation',5)
    
    for side in ['_l', '_r']:
        add_reserve(model, f'arm_flex{side}', 200)
        add_reserve(model, f'arm_add{side}', 200)
        add_reserve(model, f'arm_rot{side}', 200)
        add_reserve(model, f'elbow_flex{side}', 200)
        add_reserve(model, f'pro_sup{side}', 200)
        add_reserve(model, f'wrist_flex{side}', 200)
        add_reserve(model, f'wrist_dev{side}', 200)
        add_reserve(model, f'hip_rotation{side}', 200)
        add_reserve(model, f'hip_flexion{side}', 200)
        add_reserve(model, f'hip_adduction{side}', 200)
        add_reserve(model, f'knee_angle{side}', 200)
        add_reserve(model, f'ankle_angle{side}', 200)
    
    model.printToXML(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ sub_name +'_Scaled_'+ APP[0:4] +'_Actuator.osim')
    
    
    so = osim.AnalyzeTool(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\SO_Results\\'
                         +'SETUP_SO_' +kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_'+ APP +'.xml')
    so.setModel(model)
    so.setModelFilename(model_path)
    so.run()


root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous'
sub_name = 'SUB1'
APP = 'APP2_OneCycle'
kg_bpm = ['15_10','15_16']

for condition in range(0,2-1):
    for trial_num in range(1+1,3):
        for task_num in range(1,11):
            
            start_time=time.time()
            OneCycle_SO_RUN(root_dir, sub_name, APP, kg_bpm[condition], str(trial_num), str(task_num))
            end_time=time.time()
            
            # 실행 시간 계산 및 출력
            execution_time = end_time - start_time
            print(f"{APP} {kg_bpm[condition]}_{str(trial_num)}_12sec_{str(task_num)} SO 코드 실행 시간: {execution_time} 초")



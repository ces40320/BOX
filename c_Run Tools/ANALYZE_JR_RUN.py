import os
os.add_dll_directory("C:/OpenSim 4.4/bin")
# import numpy as np
# import pandas as pd
import opensim as osim
import time


def JR_RUN(root_dir, sub_name, APP, kg_bpm, trial_num, UpDown, task_num):
    model_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ sub_name +'_Scaled_'+ APP +'_Actuator.osim'
    model = osim.Model(model_path)
    
    analyze = osim.AnalyzeTool(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results\\'
                               +'SETUP_JR_' +kg_bpm +'_trial'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_'+ APP +'.xml')
    analyze.setModel(model)
    analyze.setModelFilename(model_path)
    analyze.run()


def JR_RUN_g(root_dir, sub_name, APP, kg_bpm, trial_num, UpDown, task_num):       # APP4 전용: EHF 추정값 획득
    model_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ sub_name +'_Scaled_'+ APP +'_Actuator.osim'
    model = osim.Model(model_path)
    
    analyze = osim.AnalyzeTool(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results\\'
                               +'SETUP_JR_' +kg_bpm +'_trial'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_'+ APP +'_ground.xml')
    analyze.setModel(model)
    analyze.setModelFilename(model_path)
    analyze.run()
    

root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous'
sub_name = 'SUB2'
APP = ['APP1','APP2','APP4']
kg_bpm = ['15_10_S','15_16']
UpDown = ['U','D']

for condition in range(0,2-1):
    for EHF in range(0,3):
        for trial_num in range(1,3-1):
            for ud in range(0+1,2):
                for task_num in range(1,11):
                    start_time=time.time()
                    
                    JR_RUN(root_dir, sub_name, APP[EHF], kg_bpm[condition], str(trial_num), UpDown[ud], str(task_num))
                    if APP[EHF] == 'APP4':
                        JR_RUN_g(root_dir, sub_name, APP[EHF], kg_bpm[condition], str(trial_num), UpDown[ud], str(task_num))    # APP4 전용
                    
                    end_time=time.time()
                    # 실행 시간 계산 및 출력
                    execution_time = end_time - start_time
                    print(f"{APP[EHF]} {kg_bpm[condition]}_{str(trial_num)}_{UpDown[ud]}{str(task_num)} JR 코드 실행 시간: {execution_time} 초")
                
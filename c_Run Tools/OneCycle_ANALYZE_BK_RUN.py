import os
os.add_dll_directory("C:/OpenSim 4.4/bin")
# import numpy as np
# import pandas as pd
import opensim as osim

def BK_RUN(root_dir, sub_name, APP, kg_bpm, trial_num, task_num):
    model_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ sub_name +'_Scaled_'+ APP[0:4] +'_Actuator.osim'
    model = osim.Model(model_path)
    
    analyze = osim.AnalyzeTool(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\BK_Results\\'
                               +'SETUP_BK_' +kg_bpm +'_trial'+ str(trial_num) +'_12sec_' + str(task_num) +'_'+ APP +'.xml')
    analyze.setModel(model)
    analyze.setModelFilename(model_path)
    analyze.run()
    

root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous'
sub_name = 'SUB1'
APP = 'APP2_OneCycle'
kg_bpm = ['15_10','15_16']

for condition in range(0,2-1):
    for trial_num in range(1,3):
        for task_num in range(1,11):
            BK_RUN(root_dir, sub_name, APP, kg_bpm[condition], str(trial_num), str(task_num))
                
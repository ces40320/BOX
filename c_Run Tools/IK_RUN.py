import os
os.add_dll_directory("C:/OpenSim 4.4/bin")
import numpy as np
import pandas as pd
import opensim as osim


def IK_RUN(root_dir, sub_name, APP, kg_bpm, trial_num, UpDown, task_num):
    trc_dir = (root_dir+'\\'+sub_name+'\\'+'UpDown_TrcMot'+'\\'
              + kg_bpm +'_trial'+ str(trial_num) +'_'+ UpDown + str(task_num) +'.trc')
    df = pd.read_csv(trc_dir, sep='\t', skiprows=4)
    trcdata = np.array(df)

    base_model = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ sub_name +'_Scaled_AddBiomech_'+ APP +'.osim'
    model = osim.Model(os.path.join(base_model))
    
    if APP == 'APP3':
        base_IK = "E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\SETUP_IK_APP3,4.xml"
    else:
        base_IK = "E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\SETUP_IK_APP1,2.xml"
    
    IK=osim.InverseKinematicsTool(base_IK)
    IK.setName(sub_name)
    IK.set_marker_file(trc_dir)
    IK.setModel(model)
    IK.setStartTime(trcdata[1,1])
    IK.setEndTime(trcdata[-1,1])
    IK.setOutputMotionFileName(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\IK_Results'+'\\'
                               + kg_bpm +'_trial'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_IK.mot')

    IK.printToXML(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\IK_Results'+'\\'
                               + 'SETUP_IK_'+ kg_bpm +'_trial'+ str(trial_num) +'_'+ UpDown + str(task_num) +'_'+ APP +'.xml')
    IK.run()


root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous'
sub_name = 'SUB2'
APP = 'APP3'
kg_bpm = ['15_10_S','15_16']
UpDown = ['U','D']

for condition in range(0,2-1):
    for trial_num in range(1,3-1):
        for ud in range(0+1,2):
            for task_num in range(1,11):
                IK_RUN(root_dir, sub_name, APP, kg_bpm[condition], trial_num, UpDown[ud], task_num)


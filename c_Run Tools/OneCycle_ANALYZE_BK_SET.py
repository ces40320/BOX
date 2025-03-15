import os
os.add_dll_directory("C:/OpenSim 4.4/bin")
import numpy as np
import pandas as pd
import opensim as osim
# from lxml import etree

def BK_SET(root_dir, sub_name, APP, kg_bpm, trial_num, task_num):
    trc_file_path = (root_dir+'\\'+sub_name+'\\'+'OneCycle_TrcMot'+'\\'
                    + kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'.trc')
    df = pd.read_csv(trc_file_path, sep='\t', skiprows=4)
    trcdata = np.array(df)

    model_path = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ sub_name +'_Scaled_'+ APP[0:4] +'_Actuator.osim'
    model = osim.Model(model_path)

    analyze = osim.AnalyzeTool()
    analyze.setName(sub_name+'_'+ kg_bpm +'_'+ str(trial_num) +'_12sec_' + str(task_num) +'_'+ APP)
    analyze.setModel(model)
    analyze.setModelFilename(model_path)
    analyze.setReplaceForceSet(False)
    analyze.setControlsFileName(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\SO_Results'+'\\'
                                + sub_name +'_'+ kg_bpm +'_'+ str(trial_num) +'_12sec_'+ str(task_num) +'_'+ APP +'_StaticOptimization_activation.sto')
    analyze.setCoordinatesFileName(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\IK_Results'+'\\'
                                   + kg_bpm +'_trial'+ str(trial_num) +'_12sec_' + str(task_num) +'_IK.mot')
    analyze.setLowpassCutoffFrequency(6)
    analyze.setSolveForEquilibrium(True)
    analyze.setStartTime(trcdata[1, 1])
    analyze.setFinalTime(trcdata[-1, 1])
    
    grf_file_path = (root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\xml_ExtLoad\\'
                     +'SETUP_ExtLoad_'+ kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_'+ APP +'.xml')
    analyze.setExternalLoadsFileName(grf_file_path)
    
    bk = osim.BodyKinematics()
    bk.setName('BodyKinematics')
    bk.setStartTime(trcdata[1, 1])
    bk.setEndTime(trcdata[-1, 1])
    bk.setStepInterval(1)
    bk.setInDegrees(True)

    analyze.getAnalysisSet().adoptAndAppend(bk)
    analyze.setResultsDir(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\BK_Results')
    # analyze.setOutputPrecision(8)
    analyze.printToXML(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\BK_Results\\'
                       +'SETUP_BK_' +kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_'+ APP +'.xml')
    
    # analyze.run()
    
    
root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous'
sub_name = 'SUB1'
APP = 'APP2_OneCycle'
kg_bpm = ['15_10','15_16']

for condition in range(0,2-1):
    for trial_num in range(1,3):
        for task_num in range(1,11):
            BK_SET(root_dir, sub_name, APP, kg_bpm[condition], str(trial_num), str(task_num))
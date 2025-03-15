import os
os.add_dll_directory("C:/OpenSim 4.4/bin")
import numpy as np
import pandas as pd
import opensim as osim
from lxml import etree

def JR_SET(root_dir, sub_name, APP, kg_bpm, trial_num, task_num):
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
                                + sub_name +'_'+ kg_bpm +'_'+ str(trial_num) +'_12sec_' + str(task_num) +'_'+ APP +'_StaticOptimization_activation.sto')
    
    if APP == 'APP4':   # 'APP4'일 때는 grf_file_path, IK 에 있는 APP변수를 'APP3'로 변경 후 실행해야 함.
        analyze.setCoordinatesFileName(root_dir +'\\'+ sub_name +'\\'+ 'APP3' +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\IK_Results'+'\\'
                                       + kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_IK.mot')
    else:
        analyze.setCoordinatesFileName(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\IK_Results'+'\\'
                                       + kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_IK.mot')
        
    analyze.setLowpassCutoffFrequency(6)
    analyze.setSolveForEquilibrium(True)
    analyze.setStartTime(trcdata[1, 1])
    analyze.setFinalTime(trcdata[-1, 1])
    
    if APP == 'APP4':   # 'APP4'일 때는 grf_file_path, IK 에 있는 APP변수를 'APP3'로 변경 후 실행해야 함.
        grf_file_path = (root_dir +'\\'+ sub_name +'\\'+ 'APP3' +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\xml_ExtLoad\\'
                        +'SETUP_ExtLoad_'+ kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_'+ APP +'.xml')
    else:
        grf_file_path = (root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\xml_ExtLoad\\'
                        +'SETUP_ExtLoad_'+ kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_'+ APP +'.xml')
    
    analyze.setExternalLoadsFileName(grf_file_path)
    
    jr = osim.JointReaction()
    jr.setName('JointReaction')
    jr.setStartTime(trcdata[1, 1])
    jr.setEndTime(trcdata[-1, 1])
    jr.setStepInterval(1)
    jr.setInDegrees(True)
    jr.setForcesFileName(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\SO_Results'+'\\'
                         + sub_name +'_'+ kg_bpm +'_'+ str(trial_num) +'_12sec_' + str(task_num) +'_'+ APP +'_StaticOptimization_force.sto')

    # childF = jr.getInFrame()
    # childF = osim.ArrayStr('child')
    # jr.setInFrame(childF)
    analyze.getAnalysisSet().adoptAndAppend(jr)
    analyze.setResultsDir(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results(ground)')
    # analyze.setOutputPrecision(8)
    analyze.printToXML(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results\\'
                       +'SETUP_JR_' +kg_bpm +'_trial'+ str(trial_num) +'_12sec_' + str(task_num) +'_'+ APP +'_ground.xml')
    
    # analyze.run()
    
    
def JR_XML_SET(root_dir, sub_name, APP, kg_bpm, trial_num, task_num):
    JR_xml=(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results\\'
            +'SETUP_JR_' +kg_bpm +'_trial'+ str(trial_num) +'_12sec_' + str(task_num) +'_'+ APP +'_ground.xml')
    tree = etree.parse(JR_xml)
    root = tree.getroot()

    # <express_in_frame> 요소 찾아서 'child'로 변경
    express_in_frame_element = root.find(".//express_in_frame")
    if express_in_frame_element is not None:
        express_in_frame_element.text = 'child'
        
    results_dir = root.find('.//results_directory')
    results_dir.text = root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results'
    # 변경된 XML 파일 저장
    tree.write(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\JR_Results\\'
                +'SETUP_JR_' +kg_bpm +'_trial'+ str(trial_num) +'_12sec_' + str(task_num) +'_'+ APP +'.xml',
                pretty_print=True, encoding="UTF-8", xml_declaration=True)
    
    

root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous'
sub_name = 'SUB1'
APP = 'APP2_OneCycle'
kg_bpm = ['15_10','15_16']

for condition in range(0,2-1):
    for trial_num in range(1,3):
        for task_num in range(1,11):
            JR_SET(root_dir, sub_name, APP, kg_bpm[condition], str(trial_num), str(task_num))

for condition in range(0,2-1):
    for trial_num in range(1,3):
        for task_num in range(1,11):
            JR_XML_SET(root_dir, sub_name, APP, kg_bpm[condition], str(trial_num), str(task_num))
    
    
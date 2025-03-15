import os
os.add_dll_directory("C:/OpenSim 4.4/bin")
# import numpy as np ; import pandas as pd
# import opensim as osim
from lxml import etree

def OneCycle_ExtLoad_XML_SET(root_dir, sub_name, APP, kg_bpm, trial_num, task_num):
    # 샘플 XML 파일 불러오기
    ExtLoad_xml="E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\SETUP_ExtLoad.xml"
    tree = etree.parse(ExtLoad_xml)
    root = tree.getroot()

    # <datafile> 요소 찾아서 변경
    datafile_element = root.find(".//datafile")
    if datafile_element is not None:
        datafile_element.text = (root_dir +'\\'+ sub_name +'\\OneCycle_TrcMot\\'
                                 + kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_ExtLoad'+ APP[0:4] +'.mot')
    # 변경된 XML 파일 저장
    tree.write(root_dir +'\\'+ sub_name +'\\'+ APP +'\\'+ 'trial'+ kg_bpm +'_'+ str(trial_num) +'\\xml_ExtLoad\\'
               +'SETUP_ExtLoad_'+ kg_bpm +'_trial'+ str(trial_num) +'_12sec_'+ str(task_num) +'_'+ APP +'.xml',
               pretty_print=True, encoding="UTF-8", xml_declaration=True)


root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous'
sub_name = 'SUB1'
APP = 'APP2_OneCycle'
kg_bpm = ['15_10','15_16']


for condition in range(0,2-1):
    for trial_num in range(1,3):
        for ud in range(0,2):
            for task_num in range(1,11):
                OneCycle_ExtLoad_XML_SET(root_dir, sub_name, APP, kg_bpm[condition], trial_num, task_num)


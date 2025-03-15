
import os; import numpy as np; import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

os.chdir(r'E:\Dropbox\SEL\Python functions\OpenSim Analysis\d_Results Analysis')
from Utils import Crop_OneCycle

root_dir = 'E:\\Dropbox\\SEL\\BOX\\OpenSim\\_Main_\\c_AddBio_Continous' #SUB1\\APP1\\trial10_15_1\\SO_Results\\
sub_name = 'SUB1'
APP_li = ['APP1']
kg_bpm = '15_10'
Result = "JR"
trial_num_li = ['1', '2']
task_num_li = list(range(1,11))

if Result == "SO":
    force_or_activation = input("force or activation? Say just F or A. : ")
    if len(force_or_activation) == 1:
        if force_or_activation == 'F' or force_or_activation == 'f':
            force_or_activation = 'force'
        elif force_or_activation == 'A' or force_or_activation == 'a':
            force_or_activation = 'activation'
    elif force_or_activation == 'force' or force_or_activation == 'activation':
        pass
    else:
        force_or_activation = input("Wrong!! Say again! F or A?? : ")

    print(f'You selected "{force_or_activation}".')
    
    result_folder = f"{Result}_Results"
    result_header = f"StaticOptimization_{force_or_activation}"
    
elif Result == "JR":
    result_folder = f"{Result}_Results"
    result_header = f"JointReaction_ReactionLoads"


for APP in APP_li:
    for trial_num in trial_num_li:
        for task_num in task_num_li:
            Up_path = os.path.join(root_dir,sub_name,APP,f"trial{kg_bpm}_{str(trial_num)}",result_folder,
                                   f"{sub_name}_{kg_bpm}_{str(trial_num)}_U{str(task_num)}_{APP}_{result_header}.sto")
            Down_path = os.path.join(root_dir,sub_name,APP,f"trial{kg_bpm}_{str(trial_num)}",result_folder,
                                     f"{sub_name}_{kg_bpm}_{str(trial_num)}_D{str(task_num)}_{APP}_{result_header}.sto")
            OneCycle_path = os.path.join(root_dir,sub_name,f"{APP}_OneCycle",f"trial{kg_bpm}_{str(trial_num)}",f"{result_folder}",
                                         f"{sub_name}_{kg_bpm}_{str(trial_num)}_12sec_{str(task_num)}_{APP}_OneCycle_{result_header}.sto")
            modified_dir = os.path.join(root_dir,sub_name,f"{APP}_Crop",f"trial{kg_bpm}_{str(trial_num)}",result_folder)
            os.makedirs(modified_dir,exist_ok=True)
            
            Crop_OneCycle(OneCycle_path, Up_path, Down_path, modified_dir)
            

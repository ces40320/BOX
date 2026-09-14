'''
Script Information:
Please read README.pdf for more info about the script.
For a comprehensive understanding of our model and methodology, please refer to
our papers:

1) Akhavanfar, M., Uchida, T. K., Clouthier, A. L., & Graham, R. B. (2022).
   Sharing the load: Modeling loads in OpenSim to simulate two-handed lifting.
   Multibody System Dynamics 54(2): 213-234. https://doi.org/10.1007/s11044-021-09808-7

2) Akhavanfar, M., Mir-Orefice, A., Uchida, T. K., & Graham, R. B. (2023).
   An enhanced spine model validated for simulating dynamic lifting tasks in OpenSim.
   Annals of Biomedical Engineering. https://doi.org/10.1007/s10439-023-03368-x
'''

import opensim as osim
import os

# User Setup:
# Specify file paths and directories.
TrialModelFilePath='C:/Akhavanfar/Squat-7/APP5/'
os.chdir(TrialModelFilePath)

# Creating P2_APP5_SO Model:
# Load the human model ('P2_APP1_SO.osim') and the box model.
LoadModel=osim.Model('Load.osim')
SkeletalModel=osim.Model('P2_APP1_SO.osim')

# Modify the inertial properties of the Load (box) to a negligible mass.
load=LoadModel.getBodySet().get("Load")
mass=0.0001
load.setMass(mass)
inertia = osim.Inertia(0.0001, 0.0001, 0.0001, 0, 0, 0)
load.setInertia(inertia)

# Add the modified Load model to the human model to create the combined model.
SkeletalModel.addBody(load)

# Print the new combined model to a file ('P2_APP5_SO.osim').
setupFile='P2_APP5_SO.osim'
SkeletalModel.printToXML(TrialModelFilePath+setupFile)

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
# Please modify to locate the Squat-7 folder on your computer.
MainDir='C:/Akhavanfar/Squat-7/'
os.chdir(MainDir)

# Creating the Box Model with Markers in Box Coordinate System:
# Load the model with markers in ground reference frame.
FileName='Load_MrkGND.osim'
myModel = osim.Model(FileName)
myModel.initSystem()
initstate=myModel.getWorkingState()
load=myModel.getBodySet().get('Load')
markers=myModel.getMarkerSet()
nummarkers=markers.getSize()
# Iterate through markers and change their body location to the box.
for kk in range (1,nummarkers+1):
    marker=markers.get(kk-1)
    marker.changeFramePreserveLocation(initstate,load)
# Initialize the model system and save it as 'Load.osim'.
myModel.initSystem()
setupFile='Load.osim'
myModel.printToXML(setupFile)

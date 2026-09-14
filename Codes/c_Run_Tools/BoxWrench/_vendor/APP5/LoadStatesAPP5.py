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

# Running States Reporter Analysis for the Box:
ModelFileName='Load.osim'
thisModel = osim.Model(ModelFileName)
# Cut-off frequency for low-pass filter.
cutoff=3
# Define prefixes and file paths.
Prefix='Load'
States_setup_file_name='LoadStatesSetup.xml'
ikloadname='IKResultsLoad.mot'
ikloadfile=TrialModelFilePath+ikloadname
# Load the IK results as a storage.
ikloadresults=osim.Storage(ikloadfile)
sTime=ikloadresults.getFirstTime()
fTime=ikloadresults.getLastTime()
# Create a States Reporter analysis.
sr = osim.StatesReporter()
sr.setOn(True)
sr.setStartTime(sTime)
sr.setEndTime(fTime)
sr.setName('StatesReporter')
# Set up the Analyze Tool and configure it for States Reporter analysis.
at = osim.AnalyzeTool()
at.setModel(thisModel)
at.setModelFilename(ModelFileName)
StatesResultsDir='LoadAnalysis'
at.setResultsDir(StatesResultsDir)
at.setInitialTime(sTime)
at.setFinalTime(fTime)
at.setSolveForEquilibrium(False)
at.setCoordinatesFileName(ikloadname)
at.setName(Prefix)
at.setLowpassCutoffFrequency(cutoff)
# Add States Reporter to the Analyze Tool.
at.getAnalysisSet().cloneAndAppend(sr)
# Print the States Reporter setup file and run the analysis.
at.printToXML(States_setup_file_name)
at = osim.AnalyzeTool(States_setup_file_name)
at.run()
# Remove the States Reporter analysis set from the model.
at.removeAnalysisSetFromModel()

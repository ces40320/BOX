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

import os
import pandas

# ============================== HELPER FUNCTION ==============================
# Reads a STO file; returns DataFrame and list of column headers.
def readStoFile(filename):
    if not os.path.exists(filename):
        raise Exception('Specified file does not exist')
    
    # Read file header and column headers.
    numHeadRows = 1
    numDataRows = 0
    numDataCols = 0
    foundEndHeader = False
    
    print('Reading', filename, '...')
    
    f = open(filename, 'r')
    
    while f:
        line = f.readline()
        if ('nRows' in line):
            numDataRows = int( line[line.index('=')+1:] )
        if ('nColumns' in line):
            numDataCols = int( line[line.index('=')+1:] )
        if ('endheader' in line):
            foundEndHeader = True
            continue
        if (not foundEndHeader):
            numHeadRows += 1
        else:
            line = line.strip()  #remove trailing line break
            colHeaders = line.split('\t')
            break
    f.close()
    
    # Check length of column label list.
    if (len(colHeaders) != numDataCols):
        raise Exception('Number of column headers inconsistent with DataFrame')
    
    # Read data.
    df = pandas.read_csv(filename, delimiter='\t', skiprows=numHeadRows)
    if ((df.shape[0] != numDataRows) or (df.shape[1] != numDataCols)):
        raise Exception('DataFrame dimensions inconsistent with file header')
    
    return df, colHeaders

# ===============================  S C R I P T  ===============================
# Please modify to locate the APP5 folder on your computer.
Dir='C:/Akhavanfar/Squat-7/APP5'
os.chdir(Dir)

# Combining the Load and Body Motion Files:
# Load the motion data from 'IKResults.mot' and 'IKResultsLoad.mot'.
filename_IK = 'IKResults.mot'
df_IK, colHeaders_IK = readStoFile(filename_IK)
filename_Load = 'IKResultsLoad.mot'
df_Load, colHeaders_IK = readStoFile(filename_Load)

# Combine the data from both motion files, keeping the time column from
# 'IKResults.mot'.
df_IK=df_IK.drop('time', axis=1)
df_IK = pandas.concat([df_Load, df_IK], axis=1)

# Write the combined motion data and text data to 'IKResultsCombined.mot':
# Define the metadata.
metadata = {
        'version': '1',
        'numRows': len(df_IK),
        'numColumns': len(df_IK.columns),
        'inDegrees': 'yes',}

# Write the metadata to file.
with open('IKResultsCombined.mot', 'w') as f:
    f.write('Coordinates\n')
    for key, value in metadata.items():
        f.write(f'{key}={value}\n')
    f.write('endheader\n')
    
    column_names = df_IK.columns
    f.write('\t'.join(column_names) + '\n')

# Append the data to the file.
df_IK.to_csv('IKResultsCombined.mot', sep='\t', index=False, header=False, mode='a')

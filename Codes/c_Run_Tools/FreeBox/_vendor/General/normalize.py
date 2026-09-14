'''
This function transforms the data into x samples evenly spaced throughout the
dataset (using PchipInterpolator for shape-preserving spline interpolation).
'''

import numpy as np
from scipy.interpolate import PchipInterpolator

def normalize(indat, numpoints):
    nframes = indat.shape[0]
    ncols = indat.shape[1]
    index = np.arange(nframes)
    
    # Construct a cycle array with exactly 'numpoints' elements.
    cycle = np.linspace(0, nframes - 1, numpoints)
    
    # Initialize the normalized data array.
    normdat = np.empty((numpoints, ncols))
    
    for i in range(ncols):
        # Use PchipInterpolator for shape-preserving spline interpolation.
        interpolator = PchipInterpolator(index, indat[:, i])
        normdat[:, i] = interpolator(cycle)
    
    return normdat

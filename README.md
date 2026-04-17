# BOX

## Installation

This project is tested with Conda environment `opensim_scripting` (Python 3.11).

### 1) Create and activate conda environment

```bash
conda create -n opensim_scripting python=3.11 numpy
conda activate opensim_scripting
```

### 2) Install OpenSim from conda channel

```bash
conda install -c opensim-org opensim
```

### 3) Install additional project packages

```bash
pip install -r requirement.txt
```

### 4) Verify installation

```bash
python -c "import opensim as osim; print(osim.GetVersionAndDate())"
python -c "import numpy, pandas, scipy; print('core packages OK')"
```

### Notes

- The base OpenSim conda setup follows the official OpenSim Python scripting guide.
- `requirement.txt` contains extra packages used in this repository on top of the base OpenSim install.
- Reference: https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53085346/Scripting+in+Python#Conda-packages


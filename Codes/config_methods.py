import os
import sys

import SUB_Info as _sub_info
NAMECODE_li = _sub_info.subjects.keys()
PROTOCOL_li = [
    _sub_info.subjects[namecode]["protocol"]
    for namecode in NAMECODE_li
]

PROTOCOL_Candidates = {
    "Symmetric": 
        {"APPs": ["APP1", "APP2", "APP3", "APP4"] , 
         "trials": 2
    },
    "Asymmetric_Pilot": 
        {"APPs": ["APP1", "APP2", "APP3", "APP4"] , 
         "trials": 2
    },
    "Asymmetric_Triangle": 
        {"APPs": ["APP1", "APP2", "APP2_preRiCTO", "APP2_postRiCTO"] , 
         "trials": 1
    },
}

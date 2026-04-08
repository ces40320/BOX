"""
피험자 정보 및 실험 설정 (전체 Analysis 공용)
  - 모든 분석 과정에정 호출되어 사용됨

각 피험자 항목에 포함되는 필드(dict key-value pairs):
"yymmdd_NAMECODE" : {
        "SUB_number"         : (int) 피험자 번호 숫자만 (e.g. 1),
        "body_mass"          : (float) 체중 (kg),
        "height"             : (int) 신장 (mm),
        "sex"                : (str) 성별 ("M" / "F"),
        "age"                : (int) 만 나이,
        "protocol"           : (str) 프로토콜 이름 (e.g. "Symmetric" / "Asymmetric_Pilot" / "Asymmetric" ),
        "conditions"         : {"7kg_10bpm":  {"order":      (int) 프로토콜 순서 (1 ~ 4),
                                               "cycles":     (int) 반복 횟수,
                                               "error_log":  (str in list) 에러 로그 (e.g. []),
                                            },
                                "15kg_10bpm": {"order":      (int) 프로토콜 순서 (1 ~ 4),
                                              "cycles":      (int) 반복 횟수,
                                              "error_log":   (str in list) 에러 로그 (e.g. ["1AB", "4CA", "11AB"]),
                                            },
                                "7kg_16bpm":  {"order":      (int) 프로토콜 순서 (1 ~ 4),
                                               "cycles":     (int) 반복 횟수,
                                               "error_log":  (str in list) 에러 로그 (e.g. ["1AB", "7BC"]),
                                            }, 
                                "15kg_16bpm": {"order":      (int) 프로토콜 순서 (1 ~ 4),
                                               "cycles":     (int) 반복 횟수,
                                               "error_log":  (str in list) 에러 로그 (e.g. ["4CA", "1AB", "11AB"]),
                                            },
                            },
    },
"""

subjects = {
    
    "240124_PJH" : { #박준홍
        "SUB_number"         : 1,
        "body_mass"          : 75.16,
        "height"             : 1740,
        "sex"                : "M",
        "age"                : 30,
        "protocol"           : "Symmetric",
        "conditions"         : {"7kg_10bpm_trial1": {"order":       3,
                                                     "cycles":      11,
                                                     "error_log":   ['4'],
                                            },
                                "7kg_10bpm_trial2": {"order":       4,
                                                     "cycles":      12,
                                                     "error_log":   ['5','10'],
                                            },
                                "15kg_10bpm_trial1": {"order":      5,
                                                      "cycles":     11,
                                                      "error_log":  ['10'],
                                            },
                                "15kg_10bpm_trial2": {"order":      6,
                                                      "cycles":     10,
                                                      "error_log":  [],
                                            }, 
                                "7kg_16bpm_trial1": {"order":       1,
                                                     "cycles":      11,
                                                     "error_log":   ['1'],
                                            },
                                "7kg_16bpm_trial2": {"order":       2,
                                                     "cycles":      12,
                                                     "error_log":   ['5', '7'],
                                            },
                                "15kg_16bpm_trial1": {"order":      7,
                                                      "cycles":     10,
                                                      "error_log":  [],
                                            },
                                "15kg_16bpm_trial2": {"order":      8,
                                                      "cycles":     10,
                                                      "error_log":  [],
                                            },
                            },
    },
    
    "260306_KTH" : { #김태영
        "SUB_number"         : 2,
        "body_mass"          : 66.74,
        "height"             : 1730,
        "sex"                : "M",
        "age"                : 22,
        "protocol"           : "Asymmetric",
        "conditions"         : {"7kg_10bpm":  {"order":      1,
                                               "cycles":     11,
                                               "error_log":  ['7AB'],
                                            },
                                "15kg_10bpm": {"order":      2,
                                              "cycles":      11,
                                              "error_log":   ['4CA'],
                                            },
                                "7kg_16bpm":  {"order":      4,
                                               "cycles":     10,
                                               "error_log":  [],
                                            }, 
                                "15kg_16bpm": {"order":      3,
                                               "cycles":     10,
                                               "error_log":  [],
                                            },
                            },
    },
    
    
    
    
    
    
    
    
    
}
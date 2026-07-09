# ai/predictor.py

import ctypes
from pathlib import Path
import numpy as np


AI_ROOT = Path(__file__).parent

SO_FILE = AI_ROOT / "lib" / "libfermentai.so"

PARAM_FILE = (
    AI_ROOT
    / "model"
    / "ferm_model_expert_fixed.param"
)

BIN_FILE = (
    AI_ROOT
    / "model"
    / "ferm_model_expert_merged.bin"
)


class FermentPredictor:

    def __init__(self):

        self.lib = ctypes.CDLL(str(SO_FILE))

        self.lib.init_ai_model.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p
        ]

        self.lib.init_ai_model.restype = ctypes.c_int

        self.lib.predict_future_curve.argtypes = [
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
        ]

        self.lib.predict_future_curve.restype = ctypes.c_int

        ret = self.lib.init_ai_model(
            str(PARAM_FILE).encode(),
            str(BIN_FILE).encode()
        )

        if ret != 0:
            raise RuntimeError("AI模型初始化失败")

        print("[AI] 模型加载成功")


    def predict(
        self,
        temp_hist,
        ph_hist,
        co2_hist,
        time_hist
    ):

        temp_hist = np.asarray(
            temp_hist,
            dtype=np.float32
        )

        ph_hist = np.asarray(
            ph_hist,
            dtype=np.float32
        )

        co2_hist = np.asarray(
            co2_hist,
            dtype=np.float32
        )

        time_hist = np.asarray(
            time_hist,
            dtype=np.float32
        )

        output = np.zeros(
            90,
            dtype=np.float32
        )

        ret = self.lib.predict_future_curve(

            temp_hist.ctypes.data_as(
                ctypes.POINTER(ctypes.c_float)
            ),

            ph_hist.ctypes.data_as(
                ctypes.POINTER(ctypes.c_float)
            ),

            co2_hist.ctypes.data_as(
                ctypes.POINTER(ctypes.c_float)
            ),

            time_hist.ctypes.data_as(
                ctypes.POINTER(ctypes.c_float)
            ),

            output.ctypes.data_as(
                ctypes.POINTER(ctypes.c_float)
            ),
        )

        if ret != 0:
            raise RuntimeError("预测失败")

        return {
            "temp": output[0:30].copy(),
            "ph": output[30:60].copy(),
            "co2": output[60:90].copy(),
        }


predictor = FermentPredictor()
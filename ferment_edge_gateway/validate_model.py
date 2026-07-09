import numpy as np

from pathlib import Path
from ai.predictor import predictor


DATA_FILE = Path("ai/model/fermentation_expert_data.npz")

LABEL_NAMES = {
    0: "normal",
    4: "cooling_fail",
    5: "oxygen_shortage",
    6: "feed_ph_shock",
    7: "contamination",
    8: "phage_lysis",
    9: "decline",
}


def mae(a, b):
    return np.mean(np.abs(a - b))


data = np.load(DATA_FILE)
all_data = data["data"]
labels = data["labels"]

print("数据集形状:", all_data.shape)
print("标签形状:", labels.shape)

for label_id, label_name in LABEL_NAMES.items():
    idxs = np.where(labels == label_id)[0]

    if len(idxs) == 0:
        print(f"\n没有找到样本: {label_name}")
        continue

    batch_idx = idxs[0]
    batch = all_data[batch_idx]

    start = 60 * 60

    hist = batch[start:start + 60]
    real_future = batch[start + 60:start + 90]

    temp_hist = hist[:, 0].astype(np.float32)
    ph_hist = hist[:, 1].astype(np.float32)
    co2_hist = hist[:, 2].astype(np.float32)
    time_hist = hist[:, 3].astype(np.float32)

    result = predictor.predict(
        temp_hist,
        ph_hist,
        co2_hist,
        time_hist
    )

    pred_temp = result["temp"]
    pred_ph = result["ph"]
    pred_co2 = result["co2"]

    real_temp = real_future[:, 0]
    real_ph = real_future[:, 1]
    real_co2 = real_future[:, 2]

    print("\n" + "=" * 60)
    print(f"样本类型: {label_name}")
    print(f"batch index: {batch_idx}")

    print(f"Temp MAE: {mae(pred_temp, real_temp):.4f}")
    print(f"pH   MAE: {mae(pred_ph, real_ph):.4f}")
    print(f"CO2  MAE: {mae(pred_co2, real_co2):.4f}")

    print("输入最后一点:")
    print(
        f"temp={temp_hist[-1]:.2f}, "
        f"ph={ph_hist[-1]:.2f}, "
        f"co2={co2_hist[-1]:.2f}"
    )

    print("真实未来最后一点:")
    print(
        f"temp={real_temp[-1]:.2f}, "
        f"ph={real_ph[-1]:.2f}, "
        f"co2={real_co2[-1]:.2f}"
    )

    print("预测未来最后一点:")
    print(
        f"temp={pred_temp[-1]:.2f}, "
        f"ph={pred_ph[-1]:.2f}, "
        f"co2={pred_co2[-1]:.2f}"
    )
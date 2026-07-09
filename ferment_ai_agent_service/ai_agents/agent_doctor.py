# ai_agents/agent_doctor.py
# 龙芯 2K1000LA 轻量版故障诊断专家
# 功能：结合当前状态 + 历史趋势 + kb_troubleshoot.txt，判断异常原因
# 不依赖 openai SDK / LangChain / FAISS

import re
from qwen_http import call_qwen, extract_json_from_text
import state

try:
    from db_service import get_recent_trend
except Exception:
    def get_recent_trend(hours=3, max_points=12):
        return "暂无历史趋势数据。"


ALLOWED_ACTIONS = set([
    "无",
    "pump_water_on",
    "pump_water_off",
    "motor_pwm_0",
    "motor_pwm_10",
    "motor_pwm_20",
    "motor_pwm_30",
    "motor_pwm_40",
    "motor_pwm_50",
    "motor_pwm_60",
    "motor_pwm_70",
    "motor_pwm_80",
    "motor_pwm_90",
    "motor_pwm_100",
])


def sanitize_action(action):
    action = str(action or "").strip()

    if action in ("", "NONE", "none", "keep"):
        return "无"

    if action in ALLOWED_ACTIONS:
        return action

    m = re.match(r"vent_angle_(\d+)$", action)
    if m:
        angle = int(m.group(1))
        if 0 <= angle <= 180:
            return "vent_angle_%d" % angle

    return "无"


def get_current_state_text():
    ds = state.DEVICE_STATE

    return (
        "【当前设备状态】\n"
        "阶段：{stage}\n"
        "温度：{temp}℃\n"
        "pH：{ph}\n"
        "CO2：{co2}%\n"
        "液位：{level}\n"
        "搅拌PWM：{motor_pwm}%\n"
        "通风窗角度：{vent_angle}度\n"
        "冷却水泵：{pump_water}\n"
        "在线状态：{status}\n"
    ).format(
        stage=ds.get("stage", "Stage 1"),
        temp=ds.get("temp", 0.0),
        ph=ds.get("ph", 0.0),
        co2=ds.get("co2", 0.0),
        level=ds.get("level", 0.0),
        motor_pwm=ds.get("motor_pwm", 0),
        vent_angle=ds.get("vent_angle", 0),
        pump_water=ds.get("pump_water", 0),
        status=ds.get("status", "offline"),
    )


def safe_get_trend():
    """
    兼容 db_service.get_recent_trend 不同版本。
    """
    try:
        return get_recent_trend(hours=3, max_points=12)
    except TypeError:
        try:
            return get_recent_trend()
        except Exception as e:
            return "历史趋势读取失败：%s" % e
    except Exception as e:
        return "历史趋势读取失败：%s" % e


def local_fallback_doctor(question):
    """
    Qwen 调用失败时的本地兜底诊断。
    """
    q = str(question or "")
    ds = state.DEVICE_STATE

    try:
        temp = float(ds.get("temp", 0.0))
        ph = float(ds.get("ph", 0.0))
        co2 = float(ds.get("co2", 0.0))
        level = float(ds.get("level", 0.0))
    except Exception:
        return {
            "text": "数据格式异常，请检查传感器。",
            "action": "无"
        }

    if level == 0:
        return {
            "text": "液位为0，疑似漏液或传感器异常。",
            "action": "无"
        }

    if "pH" in q or "PH" in q or "ph" in q or "酸" in q:
        if ph < 3.5:
            return {
                "text": "pH过低，疑似酸化或污染风险。",
                "action": "无"
            }
        if ph > 8:
            return {
                "text": "pH异常偏高，建议检查探头校准。",
                "action": "无"
            }

    if "温度" in q:
        if temp > 28:
            return {
                "text": "温度过高，建议开启冷却。",
                "action": "pump_water_on"
            }
        if temp < 10:
            return {
                "text": "温度过低，请检查环境和传感器。",
                "action": "无"
            }

    if "CO2" in q or "co2" in q or "二氧化碳" in q:
        if co2 > 95:
            return {
                "text": "二氧化碳过高，疑似排气不畅。",
                "action": "motor_pwm_100"
            }
        if co2 < 1:
            return {
                "text": "二氧化碳偏低，可能发酵活性不足。",
                "action": "无"
            }

    return {
        "text": "暂未发现明确故障，建议继续观察趋势。",
        "action": "无"
    }


def hard_abnormal_check():
    """
    程序级异常兜底。
    明显危险状态优先于大模型。
    """
    ds = state.DEVICE_STATE

    try:
        temp = float(ds.get("temp", 0.0))
        ph = float(ds.get("ph", 0.0))
        co2 = float(ds.get("co2", 0.0))
        level = float(ds.get("level", 0.0))
    except Exception:
        return None

    if level == 0:
        return {
            "text": "液位为0，疑似漏液或传感器异常。",
            "action": "无"
        }

    if temp > 28:
        return {
            "text": "温度过高，建议开启冷却。",
            "action": "pump_water_on"
        }

    if ph < 3.5:
        return {
            "text": "pH过低，疑似酸化或污染风险。",
            "action": "无"
        }

    if ph > 8:
        return {
            "text": "pH异常偏高，建议检查探头。",
            "action": "无"
        }

    if co2 > 95:
        return {
            "text": "二氧化碳过高，疑似排气不畅。",
            "action": "motor_pwm_100"
        }

    return None


def sanitize_result(result):
    text = str(result.get("text", "")).strip()
    action = sanitize_action(result.get("action", "无"))

    if not text:
        text = "故障诊断完成。"

    if len(text) > 60:
        text = text[:60]

    return {
        "text": text,
        "action": action
    }


async def run_doctor_agent(question, troubleshoot_text):
    """
    故障诊断专家：
    输入：用户问题 + kb_troubleshoot.txt 全文
    输出：{"text": "...", "action": "..."}
    """
    print("👨‍⚕️ [诊断专家] 正在接诊:", question)

    current_state = get_current_state_text()
    trend_data = safe_get_trend()
    ref = troubleshoot_text if str(troubleshoot_text or "").strip() else "无特定故障诊断指南"

    system_msg = """
你是一个工业发酵罐【故障诊断专家】。

你需要结合：
1. 当前设备状态
2. 过去3小时历史趋势
3. 故障排查知识库

判断异常原因、风险来源和建议动作。

【任务要求】
1. 如果数据明显异常，要直接指出最可能原因。
2. 如果用户问“为什么”，要结合趋势解释。
3. 如果没有明确故障，不要强行编造。
4. 回答必须适合语音播报，简短直接。
5. 总字数控制在 50 字以内。

【允许输出的 action】
只允许：
无
pump_water_on
pump_water_off
motor_pwm_0 到 motor_pwm_100，且必须是10的倍数
vent_angle_0 到 vent_angle_180

不支持的动作，例如加碱、加热、消泡剂、投料、排液、开盖，一律不要输出，action 返回 "无"。

【回复要求】
必须返回纯 JSON：
{"text":"50字以内中文诊断","action":"动作指令或无"}

不要返回 Markdown，不要解释。
"""

    user_msg = (
        current_state
        + "\n【过去3小时趋势】\n"
        + str(trend_data)
        + "\n【故障排查知识库】\n"
        + ref
        + "\n【用户问题】\n"
        + str(question or "")
    )

    try:
        content = call_qwen(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            model="qwen-turbo",
            temperature=0.2
        )

        result = extract_json_from_text(content)

        hard = hard_abnormal_check()
        if hard:
            return hard

        return sanitize_result(result)

    except Exception as e:
        print("❌ [诊断专家] 推理异常，使用本地兜底:", e)
        return local_fallback_doctor(question)
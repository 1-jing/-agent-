# ai_agents/agent_monitor.py
# 龙芯 2K1000LA 轻量版实时监控专家
# 功能：
# 1. 从 kb_device.txt 自动解析 Stage 1 / Stage 2 / Stage 3 阈值
# 2. 单项查询：先回答当前指标，再短句补充其他异常
# 3. 总体查询：只播报关键异常，不再冗长播报完整阈值
# 4. 传感器类问题不交给 Qwen，避免漏判和长回答

import re
import hashlib
from qwen_http import call_qwen, extract_json_from_text
import state


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


_RULE_CACHE = {
    "key": None,
    "rules": None
}


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


def normalize_line(line):
    line = str(line or "")

    replacements = {
        "～": "~",
        "－": "-",
        "—": "-",
        "–": "-",
        "至": "~",
        "到": "~",
        "％": "%",
        "，": ",",
        "；": ";",
        "：": ":",
        "（": "(",
        "）": ")",
    }

    for k, v in replacements.items():
        line = line.replace(k, v)

    return line.strip()


def get_current_stage():
    stage = str(state.DEVICE_STATE.get("stage", "Stage 1"))

    if "2" in stage or "二" in stage:
        return "Stage 2"

    if "3" in stage or "三" in stage:
        return "Stage 3"

    return "Stage 1"


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


def extract_range(line):
    """
    解析：
    18.0℃ ~ 22.0℃
    4.8 ~ 5.5
    0.0% ~ 5.0%
    1档 ~ 2档
    """
    line = normalize_line(line)

    m = re.search(
        r"(-?\d+(?:\.\d+)?)\s*(?:℃|%|档)?\s*[~-]\s*(-?\d+(?:\.\d+)?)",
        line
    )

    if not m:
        return None

    a = float(m.group(1))
    b = float(m.group(2))

    if a > b:
        a, b = b, a

    return (a, b)


def extract_single_level(line):
    """
    解析：
    安全状态为 1档
    """
    line = normalize_line(line)

    m = re.search(r"安全状态为\s*(\d+(?:\.\d+)?)\s*档", line)
    if not m:
        return None

    v = float(m.group(1))
    return (v, v)


def parse_device_rules(device_rules_text):
    """
    从 kb_device.txt 逐行解析安全阈值。
    只识别真正的阶段标题，避免把总则里的 Stage 1/2/3 误识别成标题。
    """
    rules = {
        "Stage 1": {},
        "Stage 2": {},
        "Stage 3": {},
    }

    current_stage = None

    for raw_line in str(device_rules_text or "").splitlines():
        line = normalize_line(raw_line)

        if not line:
            continue

        if line.startswith("【阶段一") or re.search(r"(Stage\s*1|Stage1).{0,20}阈值矩阵", line, re.I):
            current_stage = "Stage 1"
            continue

        if line.startswith("【阶段二") or re.search(r"(Stage\s*2|Stage2).{0,20}阈值矩阵", line, re.I):
            current_stage = "Stage 2"
            continue

        if line.startswith("【阶段三") or re.search(r"(Stage\s*3|Stage3).{0,20}阈值矩阵", line, re.I):
            current_stage = "Stage 3"
            continue

        if current_stage is None:
            continue

        if "温度监控" in line and "安全阈值" in line:
            rng = extract_range(line)
            if rng:
                rules[current_stage]["temp"] = rng

        elif "pH" in line and "安全阈值" in line:
            rng = extract_range(line)
            if rng:
                rules[current_stage]["ph"] = rng

        elif ("CO2" in line or "二氧化碳" in line) and "安全阈值" in line:
            rng = extract_range(line)
            if rng:
                rules[current_stage]["co2"] = rng

        elif "液位监控" in line and "安全状态" in line:
            rng = extract_range(line)
            if rng:
                rules[current_stage]["level"] = rng
            else:
                single = extract_single_level(line)
                if single:
                    rules[current_stage]["level"] = single

    print("📚 [设备知识库解析] 阶段规则：")
    for stage_name in ["Stage 1", "Stage 2", "Stage 3"]:
        rule = rules.get(stage_name, {})
        print(
            "  %s -> temp=%s, pH=%s, CO2=%s, level=%s" %
            (
                stage_name,
                rule.get("temp"),
                rule.get("ph"),
                rule.get("co2"),
                rule.get("level"),
            )
        )

    return rules


def get_parsed_rules(device_rules_text):
    """
    给知识库解析加缓存，避免每次语音请求都重新解析。
    """
    text = str(device_rules_text or "")
    key = hashlib.md5(text.encode("utf-8")).hexdigest()

    if _RULE_CACHE["key"] == key and _RULE_CACHE["rules"] is not None:
        return _RULE_CACHE["rules"]

    rules = parse_device_rules(text)

    _RULE_CACHE["key"] = key
    _RULE_CACHE["rules"] = rules

    return rules


def get_current_rule(device_rules_text):
    rules = get_parsed_rules(device_rules_text)
    stage = get_current_stage()

    return rules.get(stage, {})


def compare_value(value, safe_range):
    """
    返回：
    low / high / normal / unknown
    """
    if not safe_range:
        return "unknown"

    lo, hi = safe_range

    try:
        v = float(value)
    except Exception:
        return "unknown"

    if v < lo:
        return "low"

    if v > hi:
        return "high"

    return "normal"


def num_text(x):
    """
    让 18.0 显示成 18，4.8 保持 4.8。
    """
    try:
        x = float(x)
        if x.is_integer():
            return str(int(x))
        return str(x)
    except Exception:
        return str(x)


def range_text(safe_range, unit=""):
    if not safe_range:
        return "知识库未给出范围"

    lo, hi = safe_range

    if lo == hi:
        return "%s%s" % (num_text(lo), unit)

    return "%s到%s%s" % (num_text(lo), num_text(hi), unit)


def get_sensor_abnormal_items(device_rules_text):
    """
    根据 kb_device.txt 解析出的当前阶段阈值，逐项判断异常。
    返回长描述，用于内部判断。
    """
    ds = state.DEVICE_STATE
    rule = get_current_rule(device_rules_text)
    stage_name = get_current_stage()

    items = []

    try:
        temp = float(ds.get("temp", 0.0))
        ph = float(ds.get("ph", 0.0))
        co2 = float(ds.get("co2", 0.0))
        level = float(ds.get("level", 0.0))
    except Exception:
        return ["传感器数据格式异常"]

    temp_state = compare_value(temp, rule.get("temp"))
    if temp_state == "low":
        items.append(
            "温度%s℃低于%s安全范围%s" %
            (temp, stage_name, range_text(rule.get("temp"), "℃"))
        )
    elif temp_state == "high":
        items.append(
            "温度%s℃高于%s安全范围%s" %
            (temp, stage_name, range_text(rule.get("temp"), "℃"))
        )

    ph_state = compare_value(ph, rule.get("ph"))
    if ph_state == "low":
        items.append(
            "pH%s低于%s安全范围%s" %
            (ph, stage_name, range_text(rule.get("ph"), ""))
        )
    elif ph_state == "high":
        items.append(
            "pH%s高于%s安全范围%s" %
            (ph, stage_name, range_text(rule.get("ph"), ""))
        )

    co2_state = compare_value(co2, rule.get("co2"))
    if co2_state == "low":
        items.append(
            "二氧化碳%s%%低于%s参考范围%s" %
            (co2, stage_name, range_text(rule.get("co2"), "%"))
        )
    elif co2_state == "high":
        items.append(
            "二氧化碳%s%%高于%s参考范围%s" %
            (co2, stage_name, range_text(rule.get("co2"), "%"))
        )

    if level == 0:
        items.append("液位为0，请人工检查")
    else:
        level_state = compare_value(level, rule.get("level"))
        if level_state == "low":
            items.append(
                "液位%s档低于%s参考范围%s" %
                (level, stage_name, range_text(rule.get("level"), "档"))
            )
        elif level_state == "high":
            items.append(
                "液位%s档高于%s参考范围%s" %
                (level, stage_name, range_text(rule.get("level"), "档"))
            )

    return items


def short_abnormal_label(item):
    """
    把长异常描述压缩成适合语音播报的短标签。
    """
    item = str(item)

    if "温度" in item:
        if "低于" in item:
            return "温度偏低"
        if "高于" in item:
            return "温度偏高"
        return "温度异常"

    if "pH" in item:
        if "低于" in item:
            return "pH偏低"
        if "高于" in item:
            return "pH偏高"
        return "pH异常"

    if "二氧化碳" in item:
        if "低于" in item:
            return "二氧化碳偏低"
        if "高于" in item:
            return "二氧化碳偏高"
        return "二氧化碳异常"

    if "液位" in item:
        return "液位为0"

    return item


def compact_abnormal_text(abnormal_items, max_count=4):
    """
    总体状态查询时，把异常列表压缩成一句短话。
    """
    if not abnormal_items:
        return "各项指标正常。"

    labels = []
    for item in abnormal_items:
        label = short_abnormal_label(item)
        if label not in labels:
            labels.append(label)

    return "当前异常：" + "、".join(labels[:max_count]) + "。"


def build_extra_abnormal_warning(current_param, device_rules_text):
    """
    单项查询时，附带其他异常，但要短。
    """
    abnormal_items = get_sensor_abnormal_items(device_rules_text)

    skip_keywords = {
        "temp": ["温度"],
        "ph": ["pH"],
        "co2": ["二氧化碳", "CO2"],
        "level": ["液位"],
    }

    skips = skip_keywords.get(current_param, [])

    labels = []

    for item in abnormal_items:
        if any(k in item for k in skips):
            continue

        label = short_abnormal_label(item)
        if label not in labels:
            labels.append(label)

    if not labels:
        return ""

    return "，另有" + "、".join(labels[:2])


def abnormal_summary_for_param(param_name, device_rules_text):
    """
    单项查询时：
    1. 先回答用户问的参数是否正常
    2. 再短句补充其他异常项
    """
    ds = state.DEVICE_STATE
    rule = get_current_rule(device_rules_text)
    stage_name = get_current_stage()

    try:
        temp = float(ds.get("temp", 0.0))
        ph = float(ds.get("ph", 0.0))
        co2 = float(ds.get("co2", 0.0))
        level = float(ds.get("level", 0.0))
    except Exception:
        return "数据格式异常。"

    extra = build_extra_abnormal_warning(param_name, device_rules_text)

    if param_name == "temp":
        safe_range = rule.get("temp")
        state_name = compare_value(temp, safe_range)

        if state_name == "low":
            return "温度偏低，当前%s℃，另有%s。" % (
                temp,
                extra.replace("，另有", "") if extra else "无其他异常"
            )

        if state_name == "high":
            return "温度偏高，当前%s℃，另有%s。" % (
                temp,
                extra.replace("，另有", "") if extra else "无其他异常"
            )

        if state_name == "normal":
            if extra:
                return "温度正常，当前%s℃%s。" % (temp, extra)
            return "温度正常，当前%s℃。" % temp

        if extra:
            return "当前温度%s℃%s。" % (temp, extra)
        return "当前温度%s℃。" % temp

    if param_name == "ph":
        safe_range = rule.get("ph")
        state_name = compare_value(ph, safe_range)

        if state_name == "low":
            return "pH偏低，当前%s，另有%s。" % (
                ph,
                extra.replace("，另有", "") if extra else "无其他异常"
            )

        if state_name == "high":
            return "pH偏高，当前%s，另有%s。" % (
                ph,
                extra.replace("，另有", "") if extra else "无其他异常"
            )

        if state_name == "normal":
            if extra:
                return "pH正常，当前%s%s。" % (ph, extra)
            return "pH正常，当前%s。" % ph

        if extra:
            return "当前pH为%s%s。" % (ph, extra)
        return "当前pH为%s。" % ph

    if param_name == "co2":
        safe_range = rule.get("co2")
        state_name = compare_value(co2, safe_range)

        if state_name == "low":
            return "二氧化碳偏低，当前%s%%，另有%s。" % (
                co2,
                extra.replace("，另有", "") if extra else "无其他异常"
            )

        if state_name == "high":
            return "二氧化碳偏高，当前%s%%，另有%s。" % (
                co2,
                extra.replace("，另有", "") if extra else "无其他异常"
            )

        if state_name == "normal":
            if extra:
                return "二氧化碳正常，当前%s%%%s。" % (co2, extra)
            return "二氧化碳正常，当前%s%%。" % co2

        if extra:
            return "当前二氧化碳%s%%%s。" % (co2, extra)
        return "当前二氧化碳%s%%。" % co2

    if param_name == "level":
        if level == 0:
            extra_items = [
                short_abnormal_label(item)
                for item in get_sensor_abnormal_items(device_rules_text)
                if "液位" not in item
            ]
            extra_items = list(dict.fromkeys(extra_items))
            if extra_items:
                return "液位为0，另有%s。" % "、".join(extra_items[:2])
            return "液位为0，请人工检查。"

        safe_range = rule.get("level")
        state_name = compare_value(level, safe_range)

        if state_name == "low":
            return "液位偏低，当前%s档%s。" % (level, extra)

        if state_name == "high":
            return "液位偏高，当前%s档%s。" % (level, extra)

        if state_name == "normal":
            if extra:
                return "液位正常，当前%s档%s。" % (level, extra)
            return "液位正常，当前%s档。" % level

        if extra:
            return "当前液位%s档%s。" % (level, extra)
        return "当前液位%s档。" % level

    return ""


def direct_sensor_answer(question, device_rules_text):
    """
    传感器数值类问题直接回答，并基于 kb_device.txt 解析出的范围判断是否异常。
    """
    ds = state.DEVICE_STATE
    q = str(question or "")

    temp = ds.get("temp", 0.0)
    ph = ds.get("ph", 0.0)
    co2 = ds.get("co2", 0.0)
    level = ds.get("level", 0.0)
    motor_pwm = ds.get("motor_pwm", 0)
    vent_angle = ds.get("vent_angle", 0)

    if "二氧化碳" in q or "CO2" in q or "co2" in q:
        return {
            "diagnosis": abnormal_summary_for_param("co2", device_rules_text),
            "action": "无"
        }

    if "pH" in q or "PH" in q or "ph" in q:
        return {
            "diagnosis": abnormal_summary_for_param("ph", device_rules_text),
            "action": "无"
        }

    if "温度" in q:
        return {
            "diagnosis": abnormal_summary_for_param("temp", device_rules_text),
            "action": "无"
        }

    if "液位" in q:
        return {
            "diagnosis": abnormal_summary_for_param("level", device_rules_text),
            "action": "无"
        }

    if "搅拌" in q or "电机" in q:
        return {
            "diagnosis": "当前搅拌PWM为%s%%。" % motor_pwm,
            "action": "无"
        }

    if "通风" in q or "窗" in q or "排气" in q:
        return {
            "diagnosis": "当前通风窗角度为%s度。" % vent_angle,
            "action": "无"
        }

    if "传感器" in q or "数据" in q or "指标" in q or "状态" in q or "正常" in q:
        abnormal_items = get_sensor_abnormal_items(device_rules_text)

        if abnormal_items:
            text = compact_abnormal_text(abnormal_items)
        else:
            text = "当前温度%s℃，pH%s，二氧化碳%s%%，液位%s档，各项正常。" % (
                temp, ph, co2, level
            )

        return {
            "diagnosis": text,
            "action": "无"
        }

    return None


def local_fallback_monitor(question, device_rules_text):
    direct = direct_sensor_answer(question, device_rules_text)
    if direct:
        return direct

    ds = state.DEVICE_STATE

    return {
        "diagnosis": "温度%s℃，pH%s，二氧化碳%s%%，液位%s档。" % (
            ds.get("temp", 0.0),
            ds.get("ph", 0.0),
            ds.get("co2", 0.0),
            ds.get("level", 0.0),
        ),
        "action": "无"
    }


async def run_monitor_agent(question, device_rules_text):
    """
    实时监控专家：
    优先使用程序解析 kb_device.txt 进行确定性判断。
    传感器数值类问题不交给 Qwen，避免漏判和长回答。
    其他复杂描述再交给 Qwen 解释。
    """
    print("🩺 [实时监控专家] 正在分析:", question)

    direct = direct_sensor_answer(question, device_rules_text)
    if direct:
        return direct

    current_state = get_current_state_text()
    ref = device_rules_text if str(device_rules_text or "").strip() else "无特定设备规程"

    system_msg = """
你是一个工业级严谨的发酵罐【实时监控专家】。

要求：
1. 设备规程是唯一依据。
2. 数字范围如 5.1~5.2 表示 5.1 到 5.2，不是减法。
3. 回答必须简短，优先说结论。
4. 不要展开完整阈值，除非用户明确问阈值。
5. 传感器异常要突出关键词，例如：温度偏低、pH偏低、液位为0。

【允许输出的 action】
只允许：
无
pump_water_on
pump_water_off
motor_pwm_0 到 motor_pwm_100，且必须是10的倍数
vent_angle_0 到 vent_angle_180

如果不确定动作，action 返回 "无"。

【回复要求】
必须返回纯 JSON：
{"diagnosis":"40字以内中文播报","action":"动作指令或无"}

不要返回 Markdown，不要解释。
"""

    user_msg = (
        current_state
        + "\n【设备规程】\n"
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
            temperature=0.1
        )

        result = extract_json_from_text(content)

        diagnosis = str(result.get("diagnosis", "")).strip()
        action = sanitize_action(result.get("action", "无"))

        if not diagnosis:
            diagnosis = "状态分析完成。"

        return {
            "diagnosis": diagnosis,
            "action": action
        }

    except Exception as e:
        print("❌ [实时监控专家] 分析异常，使用本地兜底:", e)
        return local_fallback_monitor(question, device_rules_text)
# ai_agents/agent_control.py
# 龙芯 2K1000LA 轻量版控制审批专家
# 功能：
# 1. 普通控制按工艺保护
# 2. 强制/授权控制允许展示动作越权
# 3. “强制设为一档/零档/领导”默认理解为搅拌档位
# 4. 未接入动作永远拒绝

import re
from qwen_http import call_qwen, extract_json_from_text
import state


MOTOR_PWM_LEVELS = set([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])


def normalize_control_text(text):
    text = str(text or "")

    replacements = {
        "脚弯": "搅拌",
        "脚腕": "搅拌",
        "脚拌": "搅拌",
        "脚板": "搅拌",
        "胶板": "搅拌",
        "胶拌": "搅拌",
        "胶棒": "搅拌",
        "搅伴": "搅拌",
        "搅半": "搅拌",
        "交拌": "搅拌",
        "保缴纳制度": "把搅拌速度",
        "缴纳制度": "搅拌速度",

        "领导": "0档",
        "零的": "0档",
        "为零": "为0档",
        "设为零": "设为0档",
        "设为领导": "设为0档",

        "零档": "0档",
        "零挡": "0档",
        "零到": "0档",
        "一档": "1档",
        "一挡": "1档",
        "二档": "2档",
        "二挡": "2档",
        "两档": "2档",
        "两挡": "2档",
        "三档": "3档",
        "三挡": "3档",
        "四档": "4档",
        "四挡": "4档",
        "五档": "5档",
        "五挡": "5档",
        "六档": "6档",
        "六挡": "6档",
        "七档": "7档",
        "七挡": "7档",
        "八档": "8档",
        "八挡": "8档",
        "九档": "9档",
        "九挡": "9档",
        "十档": "10档",
        "十挡": "10档",
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    return text


def get_current_state_text():
    ds = state.DEVICE_STATE

    return (
        "【当前阶段】:{stage} | "
        "温度:{temp}℃, "
        "pH:{ph}, "
        "CO2:{co2}%, "
        "液位:{level}, "
        "搅拌:{motor_pwm}%, "
        "通风窗:{vent_angle}度, "
        "冷却水泵:{pump_water}"
    ).format(
        stage=ds.get("stage", "Stage 1"),
        temp=ds.get("temp", 0.0),
        ph=ds.get("ph", 0.0),
        co2=ds.get("co2", 0.0),
        level=ds.get("level", 0.0),
        motor_pwm=ds.get("motor_pwm", 0),
        vent_angle=ds.get("vent_angle", 0),
        pump_water=ds.get("pump_water", 0),
    )


def is_force_request(question):
    q = str(question or "")

    force_words = [
        "强制",
        "授权",
        "管理员授权",
        "确认越权",
        "强制执行",
        "人工确认",
        "操作员确认",
        "必须",
        "执意",
    ]

    return any(w in q for w in force_words)


def is_unsupported_target(question):
    q = str(question or "")

    unsupported_words = [
        "加碱",
        "碱液",
        "加热",
        "加温",
        "消泡",
        "消泡剂",
        "投料",
        "排液",
        "开盖",
        "清洗",
        "报警器",
        "蜂鸣器",
    ]

    return any(w in q for w in unsupported_words)


def get_requested_motor_pwm(question):
    q = normalize_control_text(question)

    has_motor_target = (
        "搅拌" in q or
        "电机" in q or
        "速度" in q or
        "转速" in q
    )

    has_level_command = (
        "档" in q and
        ("强制" in q or "设为" in q or "调到" in q or "设置" in q or "降到" in q or "升到" in q)
    )

    if not (has_motor_target or has_level_command):
        return None

    if "停止" in q or "关闭" in q or "停掉" in q or "0档" in q:
        return 0

    m = re.search(r"(\d{1,2})\s*档", q)
    if m:
        level = int(m.group(1))
        level = max(0, min(10, level))
        return level * 10

    m = re.search(r"(\d{1,3})\s*%", q)
    if m:
        pwm = int(m.group(1))
        pwm = max(0, min(100, round(pwm / 10) * 10))
        return pwm

    return None


def stage_expected_motor_pwm():
    ds = state.DEVICE_STATE
    stage = str(ds.get("stage", "Stage 1"))

    if "1" in stage:
        return 80
    if "2" in stage:
        return 20
    if "3" in stage:
        return 40

    return None


def sanitize_action(action):
    action = str(action or "").strip()

    if action in ("", "无", "NONE", "none", "keep"):
        return "无"

    m = re.match(r"motor_pwm_(\d+)$", action)
    if m:
        pwm = int(m.group(1))
        if pwm in MOTOR_PWM_LEVELS:
            return "motor_pwm_%d" % pwm
        return "无"

    m = re.match(r"vent_angle_(\d+)$", action)
    if m:
        angle = int(m.group(1))
        if 0 <= angle <= 180:
            return "vent_angle_%d" % angle
        return "无"

    if action in ("pump_water_on", "pump_water_off"):
        return action

    return "无"


def fallback_extract_control(question):
    q = normalize_control_text(question)

    if is_unsupported_target(q):
        return {
            "text": "该动作暂不支持。",
            "action": "无"
        }

    force = is_force_request(q)

    if not force:
        return {
            "text": "当前阶段不建议执行。",
            "action": "无"
        }

    requested_pwm = get_requested_motor_pwm(q)
    if requested_pwm is not None and requested_pwm in MOTOR_PWM_LEVELS:
        return {
            "text": "已按授权执行。",
            "action": "motor_pwm_%d" % requested_pwm
        }

    if "通风" in q or "排气" in q or "窗" in q or "阀" in q:
        if "关闭" in q or "关上" in q:
            return {
                "text": "已按授权执行。",
                "action": "vent_angle_0"
            }

        if "半开" in q or "一半" in q:
            return {
                "text": "已按授权执行。",
                "action": "vent_angle_90"
            }

        if "打开" in q or "开启" in q or "全开" in q:
            return {
                "text": "已按授权执行。",
                "action": "vent_angle_180"
            }

        m = re.search(r"(\d{1,3})\s*(度|°)", q)
        if m:
            angle = int(m.group(1))
            angle = max(0, min(180, angle))
            return {
                "text": "已按授权执行。",
                "action": "vent_angle_%d" % angle
            }

    if "水泵" in q or "冷却" in q:
        if "打开" in q or "开启" in q or "启动" in q:
            return {
                "text": "已按授权执行。",
                "action": "pump_water_on"
            }

        if "关闭" in q or "停止" in q:
            return {
                "text": "已按授权执行。",
                "action": "pump_water_off"
            }

    return {
        "text": "该动作暂不支持。",
        "action": "无"
    }


def hard_safety_check_before_return(question, result):
    q = normalize_control_text(question)
    force = is_force_request(q)

    text = str(result.get("text", "")).strip()
    action = sanitize_action(result.get("action", "无"))

    if is_unsupported_target(q):
        return {
            "text": "该动作暂不支持。",
            "action": "无"
        }

    requested_pwm = get_requested_motor_pwm(q)
    expected_pwm = stage_expected_motor_pwm()

    if not force and requested_pwm is not None and expected_pwm is not None:
        if requested_pwm != expected_pwm:
            expected_level = int(expected_pwm / 10)
            return {
                "text": "当前阶段建议%d档搅拌。" % expected_level,
                "action": "无"
            }

    if not force and ("授权" in text or "强制" in text):
        if action != "无":
            text = "已按工艺要求执行。"
        else:
            text = "当前阶段不建议执行。"

    if force and action != "无":
        return {
            "text": "已按授权执行。",
            "action": action
        }

    if action == "无":
        return {
            "text": text or "当前阶段不建议执行。",
            "action": "无"
        }

    return {
        "text": text or "控制审批完成。",
        "action": action
    }


async def run_control_agent(question, device_text, recipe_text):
    print("👮‍♂️ [操作审批专家] 正在评估控制请求:", question)

    q = normalize_control_text(question)
    current_state = get_current_state_text()

    ref = (
        "【设备规程】\n"
        + str(device_text or "无设备规程")
        + "\n\n【工艺配方】\n"
        + str(recipe_text or "无工艺配方")
    )

    system_msg = """
你是一个工业发酵罐的【安全控制审批专家】。

你需要根据当前状态、设备规程和工艺配方判断用户控制指令是否允许执行。

【普通控制模式】
如果用户只是普通控制，例如：
- 把搅拌调到7档
- 关闭水泵
- 打开通风窗
- 把排气阀调到90度

你必须结合当前阶段工艺和安全规程判断是否允许。
如果当前阶段不建议执行，必须拒绝，action 返回 "无"。
普通控制模式绝对不能回复“已按授权执行”。

【授权强制模式】
只有当用户语句中明确出现以下任意词：
- 强制
- 授权
- 管理员授权
- 确认越权
- 强制执行
- 人工确认
- 操作员确认
- 必须
- 执意

才认为操作员已经授权越权执行。
此时只要动作属于展示支持范围，就必须放行，不再因为工艺阶段拒绝。

【展示支持动作】
只允许输出以下动作：
1. 搅拌速度：motor_pwm_0、motor_pwm_10、motor_pwm_20、...、motor_pwm_100
2. 通风窗/排气阀：vent_angle_0 到 vent_angle_180
3. 冷却水泵：pump_water_on、pump_water_off
4. 拒绝或无动作：无

【不支持动作】
加碱、加热、消泡剂、投料、排液、开盖、清洗、报警器等，一律拒绝，action 返回 "无"。
即使用户说强制，也不能输出这些动作。

【动作转化规则】
1. 搅拌0档输出 motor_pwm_0。
2. 搅拌1档到10档分别输出 motor_pwm_10 到 motor_pwm_100。
3. 停止搅拌、关闭电机输出 motor_pwm_0。
4. 打开通风窗、打开排气阀、全开输出 vent_angle_180。
5. 关闭通风窗、关闭排气阀输出 vent_angle_0。
6. 半开通风窗、半开排气阀输出 vent_angle_90。
7. 通风窗调到X度输出 vent_angle_X，X限制在0到180。
8. 打开冷却水泵输出 pump_water_on。
9. 关闭冷却水泵输出 pump_water_off。

【回复要求】
必须返回纯 JSON：
{"text":"20字以内中文播报","action":"机器指令或无"}

text 不能出现 motor_pwm、vent_angle、pump_water 等机器代码。
普通拒绝时，text 简短说明原因。
授权强制模式放行时，text 回复“已按授权执行。”
不要返回 Markdown，不要返回解释。
"""

    user_msg = (
        current_state
        + "\n\n"
        + ref
        + "\n\n【用户控制请求】\n"
        + q
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

        return hard_safety_check_before_return(q, result)

    except Exception as e:
        print("❌ [操作审批专家] 审批异常，进入兜底:", e)
        return fallback_extract_control(q)
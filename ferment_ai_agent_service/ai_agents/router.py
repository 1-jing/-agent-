# ai_agents/router.py
# 龙芯 2K1000LA 轻量版路由器
# 功能：control / device / recipe / troubleshoot / ignore 分诊
# 特点：
# 1. 先用本地规则抓高置信控制指令
# 2. 再用 Qwen 做语义分诊
# 3. Qwen 失败时使用本地规则兜底

from qwen_http import call_qwen, extract_json_from_text


VALID_INTENTS = ["control", "device", "troubleshoot", "recipe", "ignore"]


def normalize_router_text(question: str) -> str:
    q = str(question or "").strip()

    replacements = {
        "领导": "零档",
        "零的": "零档",
        "为零": "为零档",
        "设为领导": "设为零档",
        "保缴纳制度": "把搅拌速度",
        "缴纳制度": "搅拌速度",
        "成长本机": "当前本机",
        "传感器数据。": "传感器数据是多少？",
    }

    for k, v in replacements.items():
        q = q.replace(k, v)

    return q


def rule_fallback_intent(question: str) -> str:
    q = normalize_router_text(question)

    if not q or len(q) <= 1:
        return "ignore"

    control_words = [
        "打开", "开启", "关闭", "停止", "停掉",
        "调到", "设置", "设为", "强制", "授权",
        "执行", "升到", "降到", "调节", "开到",
        "必须", "执意"
    ]

    control_targets = [
        "搅拌", "电机", "速度", "转速",
        "水泵", "冷却", "排气", "通风", "窗", "阀",

        # 虽然这些动作不支持，但仍属于控制请求，应该交给 control agent 去拒绝
        "加碱", "碱液", "加热", "加温", "消泡", "消泡剂",
        "投料", "排液", "开盖", "清洗", "报警器", "蜂鸣器"
    ]

    unsupported_control_targets = [
        "加碱", "碱液", "加热", "加温", "消泡", "消泡剂",
        "投料", "排液", "开盖", "清洗", "报警器", "蜂鸣器"
    ]

    if any(t in q for t in unsupported_control_targets):
        return "control"

    if any(w in q for w in control_words) and any(t in q for t in control_targets):
        return "control"

    # 容错：强制设为一档 / 强制设为零档 / 强制设为领导
    if (
        ("调到" in q or "降到" in q or "升到" in q or "设置" in q or "设为" in q or "强制" in q)
        and ("档" in q or "零档" in q)
    ):
        return "control"

    trouble_words = [
        "故障", "异常", "原因", "诊断", "趋势", "风险",
        "污染", "堵塞", "停滞", "失效",
        "为什么下降", "为什么上升", "掉得", "涨得",
        "为什么", "是不是出问题"
    ]

    if any(w in q for w in trouble_words):
        return "troubleshoot"

    device_words = [
        "当前", "现在", "状态", "指标", "数据",
        "传感器", "温度", "pH", "PH", "ph",
        "二氧化碳", "CO2", "co2",
        "液位", "正常吗", "搅拌", "通风窗", "水泵"
    ]

    if any(w in q for w in device_words):
        return "device"

    recipe_words = [
        "阶段", "第一阶段", "第二阶段", "第三阶段",
        "工艺", "配方", "目标", "参数",
        "发酵目标", "控制在多少", "怎么注意",
        "主发酵", "后熟", "启动期"
    ]

    if any(w in q for w in recipe_words):
        return "recipe"

    # 很短且没有工业词的，认为是噪声
    if len(q) <= 4:
        return "ignore"

    return "recipe"


async def classify_intent(question: str) -> str:
    q = normalize_router_text(question)

    # 高置信控制指令先走本地规则，避免 Qwen 把“强制设为一档”判成 ignore
    local_intent = rule_fallback_intent(q)
    if local_intent == "control":
        return "control"

    system_msg = """你是一个抗干扰能力极强的工业发酵网关路由分发器。

前端 ASR 可能产生错别字，例如：
- “搅拌”可能识别成“脚板、脚弯、胶板”
- “调到7档”可能被拆开或带有杂音
- 用户可能只说半句或含有语气词

你必须忽略无意义噪声，只抓取核心工业意图。

请精准分类到以下五个场景：
1. "control"：设备控制指令。比如调搅拌档位、开关水泵、开关通风窗、排气阀角度、强制执行。
2. "device"：设备监控。比如询问当前温度、pH、CO2、液位、传感器数据、状态是否正常。
3. "recipe"：工艺配方。比如询问第一阶段目标、第二阶段参数、发酵工艺。
4. "troubleshoot"：故障诊断。比如询问异常原因、历史趋势、pH为什么下降、CO2异常。
5. "ignore"：无意义噪声或完全无法判断的碎片。

要求：
只返回 JSON，不要任何解释。
格式：{"intent": "control/device/recipe/troubleshoot/ignore"}
"""

    try:
        content = call_qwen(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": q}
            ],
            model="qwen-turbo",
            temperature=0.0
        )

        result = extract_json_from_text(content)
        intent = result.get("intent", "device")

        if intent not in VALID_INTENTS:
            intent = local_intent

        # 本地规则认为是 device/troubleshoot 时，优先纠偏
        if local_intent in ("device", "troubleshoot") and intent in ("ignore", "recipe"):
            return local_intent

        return intent

    except Exception as e:
        print("⚠️ [路由器] Qwen分诊失败，使用本地规则兜底:", e)
        return local_intent
# ai_agents/agent_expert.py
# 龙芯 2K1000LA 轻量版工艺专家
# 功能：回答发酵阶段、工艺参数、操作目标等问题
# 不依赖 openai SDK / LangChain / FAISS

from qwen_http import call_qwen, extract_json_from_text
import state


def get_current_state_text():
    ds = state.DEVICE_STATE

    return (
        "【当前设备参考】\n"
        "阶段：{stage}\n"
        "温度：{temp}℃\n"
        "pH：{ph}\n"
        "CO2：{co2}%\n"
        "液位：{level}\n"
        "搅拌PWM：{motor_pwm}%\n"
    ).format(
        stage=ds.get("stage", "Stage 1"),
        temp=ds.get("temp", 0.0),
        ph=ds.get("ph", 0.0),
        co2=ds.get("co2", 0.0),
        level=ds.get("level", 0.0),
        motor_pwm=ds.get("motor_pwm", 0),
    )


def local_fallback_expert(question):
    """
    Qwen 调用失败时的本地兜底。
    只回答最常见的三阶段工艺问题。
    """
    q = str(question or "")

    if "第一阶段" in q or "阶段一" in q or "启动" in q:
        return {
            "text": "第一阶段目标是启动菌种，有氧增殖，建议8档搅拌。",
            "action": "无"
        }

    if "第二阶段" in q or "阶段二" in q or "主发酵" in q:
        return {
            "text": "第二阶段是主发酵期，控温22到23度，低速搅拌防剪切。",
            "action": "无"
        }

    if "第三阶段" in q or "阶段三" in q or "后熟" in q:
        return {
            "text": "第三阶段是后熟期，控温约24度，4档搅拌防沉降。",
            "action": "无"
        }

    if "搅拌" in q:
        return {
            "text": "搅拌档位随阶段变化，启动期高搅拌，主发酵期低搅拌。",
            "action": "无"
        }

    if "温度" in q:
        return {
            "text": "不同阶段温度不同，启动期约20度，主发酵22到23度，后熟约24度。",
            "action": "无"
        }

    if "pH" in q or "PH" in q or "ph" in q:
        return {
            "text": "pH随阶段逐步降低，启动期约5.0，主发酵约4.2到4.5。",
            "action": "无"
        }

    return {
        "text": "工艺参数需结合当前发酵阶段判断。",
        "action": "无"
    }


def sanitize_result(result):
    """
    工艺专家只回答，不直接控制硬件。
    """
    text = str(result.get("text", "")).strip()

    if not text:
        text = "工艺参数需结合当前阶段判断。"

    # 防止回复太长，语音播报不舒服
    if len(text) > 60:
        text = text[:60]

    return {
        "text": text,
        "action": "无"
    }


async def run_expert_agent(question, recipe_text):
    """
    工艺专家：
    输入：用户问题 + kb_recipe.txt 全文
    输出：{"text": "...", "action": "无"}
    """
    print("👨‍🔬 [工艺专家] 正在接诊:", question)

    current_state = get_current_state_text()
    ref = recipe_text if str(recipe_text or "").strip() else "无特定工艺配方"

    system_msg = """
你是一个生物发酵工艺专家。

你需要根据【当前设备参考】和【工艺配方知识库】回答用户问题。

【任务范围】
你只回答：
1. 发酵阶段目标
2. 温度、pH、CO2、液位、搅拌档位等工艺参数
3. 各阶段操作原因
4. 阶段切换和工艺注意事项

你不直接控制设备，所以 action 永远返回 "无"。

【回答风格】
1. 面向现场操作人员，简短直接。
2. 不要长篇解释。
3. 中文回答，严格控制在 50 字以内。
4. 不要编造知识库外的复杂工艺。

【回复要求】
必须返回纯 JSON：
{"text":"50字以内中文工艺解答","action":"无"}

不要返回 Markdown，不要解释。
"""

    user_msg = (
        current_state
        + "\n【工艺配方知识库】\n"
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
            temperature=0.3
        )

        result = extract_json_from_text(content)
        return sanitize_result(result)

    except Exception as e:
        print("❌ [工艺专家] 推理异常，使用本地兜底:", e)
        return local_fallback_expert(question)
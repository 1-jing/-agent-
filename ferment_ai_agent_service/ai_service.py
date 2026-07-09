# ai_service.py
# 龙芯 2K1000LA 轻量版 AI 调度器
# 保留：router + 四大 Agent 架构
# 当前：control 已迁移完成；monitor/expert/doctor 后续逐个替换

import os
from ai_agents.router import classify_intent
from ai_agents.agent_control import run_control_agent


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")


def read_kb(filename):
    path = os.path.join(KB_DIR, filename)

    if not os.path.exists(path):
        print("⚠️ 知识库文件不存在:", path)
        return ""

    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print("❌ 读取知识库失败:", path, e)
        return ""


DEVICE_KB_TEXT = read_kb("kb_device.txt")
RECIPE_KB_TEXT = read_kb("kb_recipe.txt")
TROUBLESHOOT_KB_TEXT = read_kb("kb_troubleshoot.txt")


async def get_ai_reply(question: str) -> dict:
    """
    统一入口：
    龙芯语音识别后的文本进来，经过 router 分诊，再交给对应 Agent。
    """
    intent = await classify_intent(question)
    print("🚥 [本机智能调度] 护士分诊结果:", intent)

    if intent == "ignore":
        return {
            "text": "",
            "action": "无",
            "is_ignore": True
        }

    try:
        if intent == "control":
            res = await run_control_agent(
                question,
                DEVICE_KB_TEXT,
                RECIPE_KB_TEXT
            )

        elif intent == "device":
            # 后续迁移 agent_monitor.py 后会正式启用
            try:
                from ai_agents.agent_monitor import run_monitor_agent
                res = await run_monitor_agent(question, DEVICE_KB_TEXT)

                # 兼容你原来的 monitor 返回 diagnosis 字段
                if "diagnosis" in res and "text" not in res:
                    res = {
                        "text": res.get("diagnosis", "状态分析异常。"),
                        "action": res.get("action", "无")
                    }

            except Exception as e:
                print("⚠️ [监控Agent] 尚未完成轻量迁移或运行异常:", e)
                res = {
                    "text": "监控模块正在迁移中。",
                    "action": "无"
                }

        elif intent == "recipe":
            # 后续迁移 agent_expert.py 后会正式启用
            try:
                from ai_agents.agent_expert import run_expert_agent
                res = await run_expert_agent(question, RECIPE_KB_TEXT)
            except Exception as e:
                print("⚠️ [工艺Agent] 尚未完成轻量迁移或运行异常:", e)
                res = {
                    "text": "工艺专家模块正在迁移中。",
                    "action": "无"
                }

        elif intent == "troubleshoot":
            # 后续迁移 agent_doctor.py 后会正式启用
            try:
                from ai_agents.agent_doctor import run_doctor_agent
                res = await run_doctor_agent(question, TROUBLESHOOT_KB_TEXT)
            except Exception as e:
                print("⚠️ [诊断Agent] 尚未完成轻量迁移或运行异常:", e)
                res = {
                    "text": "故障诊断模块正在迁移中。",
                    "action": "无"
                }

        else:
            res = {
                "text": "暂时无法识别问题类型。",
                "action": "无"
            }

    except Exception as e:
        print("❌ [AI调度器] 运行异常:", e)
        res = {
            "text": "本机智能服务异常。",
            "action": "无"
        }

    return {
        "text": res.get("text", "系统暂时异常。"),
        "action": res.get("action", "无"),
        "is_ignore": False
    }
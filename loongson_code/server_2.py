import os
import json
import base64
import asyncio
import dashscope
import uvicorn
import re
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI
from dashscope.audio.tts import SpeechSynthesizer
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
 
# RAG 组件
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import CharacterTextSplitter
 
# ================= 配置区 =================
API_KEY = "sk-80e650ae1fa243988888bda818226761"
os.environ["DASHSCOPE_API_KEY"] = API_KEY
dashscope.api_key = API_KEY
 
app = FastAPI()
client = AsyncOpenAI(api_key=API_KEY, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
 
# ================= 知识库初始化 =================
vector_db = None
if os.path.exists("knowledge.txt"):
    try:
        loader = TextLoader("knowledge.txt", encoding="utf-8")
        split_docs = CharacterTextSplitter(chunk_size=100, chunk_overlap=20).split_documents(loader.load())
        vector_db = FAISS.from_documents(split_docs, DashScopeEmbeddings(model="text-embedding-v1"))
        print("✅ 知识库加载成功")
    except Exception as e:
        print(f"❌ 知识库加载出错: {e}")
 
# ================= AI 逻辑 (RAG优先 + LLM兜底) =================
# [修改] 新增 sensor_data 参数，将传感器数据注入到系统提示词中
async def get_ai_reply(question: str, sensor_data: Optional[dict] = None) -> dict:
    ref = "无规程"
    if vector_db:
        docs = vector_db.similarity_search(question, k=1)
        if docs:
            ref = docs[0].page_content
 
    # [修改] 构建传感器上下文字符串
    if sensor_data and sensor_data.get("T") is not None:
        temp = sensor_data["T"]
        humi = sensor_data["H"]
 
        # 根据阈值生成状态描述，便于 AI 直接判断
        temp_status = "偏高（超过30°C警戒值）" if temp > 30 else "正常"
        humi_status = "偏高（超过90%警戒值）" if humi >= 90 else "正常"
 
        sensor_context = (
            f"【实时传感器数据】温度：{temp}°C（状态：{temp_status}），"
            f"湿度：{humi}%（状态：{humi_status}）。"
        )
    else:
        sensor_context = "【实时传感器数据】当前暂无传感器数据。"
 
    system_msg = f"""你是一个智能发酵辅助控制仪的 AI 核心。
{sensor_context}
参考规程：{ref}



【硬件控制权限】
你连接着一个物理排气降温阀门（底层硬件由SG90舵机驱动）。你有权直接控制它！

【严格要求】
1. 诊断(diagnosis)和动作(action)均须使用中文，且限15字内。
2. 如果不需要控制硬件，action 严格返回 "无"。
3. 只准返回严格的 JSON 格式，示例：{{"diagnosis": "温湿度正常", "action": "无"}}
4. 【核心控制逻辑 1】：当温度超过30°C、或湿度超过90%、或用户明确要求“开阀门/转舵机/降温”时，你在 action 字段必须严格输出：“打开排气阀”。
5. 【核心控制逻辑 2】：当温度恢复正常，或用户主动要求“关闭”时，action 字段必须严格输出：“关闭排气阀”。

注意：用户语音可能存在同音字（如把"舵机"听成"多机"），请结合上下文理解。"""
 
    try:
        res = await client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": question}],
            temperature=0.1
        )
        content = res.choices[0].message.content.strip()
        clean_json = content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"❌ AI解析出错: {e}")
        return {"diagnosis": "指令不明", "action": "无"}
 
# ================= WebSocket 闭环 =================
@app.websocket("/ws/voice_device")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"✅ 客户端已连接: {websocket.client.host}")
 
    loop = asyncio.get_running_loop()
    task_queue = asyncio.Queue()
 
    # [新增] 用于存储本连接最新一帧传感器数据的字典
    latest_sensor: dict = {"T": None, "H": None}
 
    class RealtimeCallback(RecognitionCallback):
        def on_event(self, result: RecognitionResult):
            sent = result.get_sentence()
            if sent:
                text = sent['text']
                print(f"🎙 实时听写: {text}", end='\r')
 
                if result.is_sentence_end(sent):
                    clean_text = re.sub(r'[^\w\u4e00-\u9fa5]', '', text)
                    if len(clean_text) >= 2:
                        # [修改] 将当前传感器快照一并打包入队列
                        asyncio.run_coroutine_threadsafe(
                            task_queue.put({"text": text, "sensor": dict(latest_sensor)}),
                            loop
                        )
                    else:
                        print(f"\n⚠️ [忽略环境短噪音: {text}]")
 
    cb = RealtimeCallback()
    reg = Recognition(model='paraformer-realtime-v1', format='pcm', sample_rate=16000, callback=cb)
    reg.start()
 
    def sync_tts(text):
        return SpeechSynthesizer.call(model='sambert-zhichu-v1', format='pcm', sample_rate=16000, text=text)
 
    async def process_ai_queue():
        """后台独立协程：排队处理每一句话"""
        while True:
            # [修改] 从队列取出的是包含 text 和 sensor 的字典
            item = await task_queue.get()
            q_text = item["text"]
            sensor = item["sensor"]
 
            print(f"\n🗣️ 捕获完整指令: {q_text}")
            if sensor.get("T") is not None:
                print(f"🌡️ 当前传感器: 温度={sensor['T']}°C  湿度={sensor['H']}%")
 
            # [修改] 将传感器数据传入 AI
            ai_obj = await get_ai_reply(q_text, sensor_data=sensor)
            diag_txt = ai_obj.get("diagnosis", "未识别")
            act_txt = ai_obj.get("action", "无")
 
            if act_txt != "无":
                full_voice_txt = f"{diag_txt}。执行动作：{act_txt}"
            else:
                full_voice_txt = diag_txt
 
            print(f"🤖 播报内容: {full_voice_txt}")
 
            tts = await loop.run_in_executor(None, sync_tts, full_voice_txt)
 
            try:
                await websocket.send_json({
                    "action": act_txt,
                    "text": full_voice_txt,
                    "audio": base64.b64encode(tts.get_audio_data()).decode() if tts.get_audio_data() else ""
                })
                print("✅ 回复已发送完毕！\n" + "-"*40)
            except Exception as e:
                print(f"❌ 发送失败: {e}")
 
    ai_task = asyncio.create_task(process_ai_queue())
 
    try:
        while True:
            raw_data = await websocket.receive_text()
            packets = raw_data.strip().split('\n')
 
            for packet in packets:
                if not packet.strip():
                    continue
                try:
                    msg = json.loads(packet)
                    data = msg.get("data", {})
 
                    # [新增] 解析客户端上传的传感器数据，实时更新 latest_sensor
                    if "sensor" in data:
                        s = data["sensor"]
                        if s.get("T") is not None and s.get("H") is not None:
                            latest_sensor["T"] = s["T"]
                            latest_sensor["H"] = s["H"]
                            print(f"\r📊 传感器更新 → T={s['T']}°C  H={s['H']}%", end='')
 
                    # 处理音频帧
                    audio_b64 = data.get("audio", "")
                    if audio_b64:
                        reg.send_audio_frame(base64.b64decode(audio_b64))
 
                except Exception as e:
                    print(f"\n⚠️ 帧数据处理异常: {e}")
 
    except WebSocketDisconnect:
        print("\n❌ 客户端断开")
    finally:
        reg.stop()
        ai_task.cancel()
 
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
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
async def get_ai_reply(question: str, sensor_data: Optional[dict] = None) -> dict:
    ref = "当前无特定规程，请根据常识安全回复。"
    if vector_db:
        # 从知识库中检索与问题最相关的规程
        docs = vector_db.similarity_search(question, k=1)
        if docs:
            ref = docs[0].page_content
 
    # 构建纯客观的传感器上下文，不做任何主观判定
    sensor_context = "【实时传感器快照】"
    if sensor_data:
        temp = sensor_data.get("T", "未知")
        humi = sensor_data.get("H", "未知")
        ph = sensor_data.get("pH", "未知") 
        sensor_context += f"温度：{temp}°C，湿度：{humi}%，pH值：{ph}。"
    else:
        sensor_context += "当前暂无传感器数据。"
 
    # 全新的 System Prompt：增加数据播报专属逻辑与纯中文强制要求


    system_msg = f"""你是一个智能发酵仪表控制核心。
{sensor_context}

【最高指令规程（知识库）】
{ref}

【核心决策逻辑】
1. 规程触发：如果【实时传感器快照】的数据命中了规程中的报警阈值，必须强制执行规程动作。
2. 用户指令优先：如果用户明确下令（如“打开排气阀”、“开启舵机”），即使当前传感器数据正常，你也必须服从指令执行动作，不得以“未定义”为由拒绝！
3. 动作字段格式：执行动作时，action 必须包含“打开”或“关闭”中文字样（如：打开排气阀）。如果不涉及硬件控制，action 严格返回 "无"。
4. 语言规范：diagnosis 字段必须是纯中文，严禁英文。简短有力，15字以内。
5. 数据查询：用户问数据时（如“现在几度”），如实播报快照数值，action 为 "无"。

只准返回纯净 JSON！
示例：{{"diagnosis": "已为您手动打开排气阀", "action": "打开排气阀"}}
"""
 
    try:
        res = await client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": question}],
            temperature=0.01 
        )
        content = res.choices[0].message.content.strip()
        clean_json = content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"❌ AI解析出错: {e}")
        return {"diagnosis": "系统思考异常", "action": "无"}
 
# ================= WebSocket 闭环 =================
@app.websocket("/ws/voice_device")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"✅ 客户端已连接: {websocket.client.host}")
 
    loop = asyncio.get_running_loop()
    task_queue = asyncio.Queue()
 
    # 用于存储本连接最新一帧传感器数据的字典
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
                        asyncio.run_coroutine_threadsafe(
                            task_queue.put({"text": text, "sensor": dict(latest_sensor)}),
                            loop
                        )
                    else:
                        print(f"\n⚠️ [忽略环境短噪音: {text}]")
 
    cb = RealtimeCallback()
    
    # 这里的 ASR 听写必须保持 pcm (生肉) 接收龙芯发来的音频流
    reg = Recognition(model='paraformer-realtime-v1', format='pcm', sample_rate=16000, callback=cb)
    reg.start()
 
    def sync_tts(text):
        # 【！！！关键修复：把 format='pcm' 改成了 format='wav' ！！！】
        # 这样阿里云就会生成带有标准头文件的熟肉音频，发给龙芯后就不会爆音崩溃了
        return SpeechSynthesizer.call(model='sambert-zhichu-v1', format='wav', sample_rate=16000, text=text)
 
    async def process_ai_queue():
        """后台独立协程：排队处理每一句话"""
        while True:
            item = await task_queue.get()
            q_text = item["text"]
            sensor = item["sensor"]
 
            print(f"\n🗣️ 捕获完整指令: {q_text}")
            if sensor.get("T") is not None:
                print(f"🌡️ 当前传感器: 温度={sensor['T']}°C  湿度={sensor['H']}%")
 
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
 
                    # 解析客户端上传的传感器数据，实时更新 latest_sensor
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
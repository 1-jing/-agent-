import os
import json
import base64
import asyncio
import dashscope
import uvicorn
import re
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
async def get_ai_reply(question: str) -> dict:
    ref = "无规程"
    if vector_db:
        docs = vector_db.similarity_search(question, k=1)
        if docs: 
            ref = docs[0].page_content

    system_msg = f"""你是一个工业助理。参考规程：{ref}
要求：
1.诊断(diagnosis)和动作(action)均须使用中文，且限15字内。
2.如果没有动作则action返回"无"。
3.只准返回严格的JSON格式。
注意：用户语音可能存在同音字（如把"发酵罐"识别成"八角管"），请根据工业场景自动纠正。"""

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

    class RealtimeCallback(RecognitionCallback):
        def on_event(self, result: RecognitionResult):
            sent = result.get_sentence()
            if sent:
                text = sent['text']
                print(f"🎙 实时听写: {text}", end='\r')
                
                if result.is_sentence_end(sent):
                    # 【核心过滤】：剔除标点，字数<2视为噪音丢弃
                    clean_text = re.sub(r'[^\w\u4e00-\u9fa5]', '', text)
                    if len(clean_text) >= 2:
                        asyncio.run_coroutine_threadsafe(task_queue.put(text), loop)
                    else:
                        print(f"\n⚠️ [忽略环境短噪音: {text}]")

    cb = RealtimeCallback()
    reg = Recognition(model='paraformer-realtime-v1', format='pcm', sample_rate=16000, callback=cb)
    reg.start()

    # 将同步的 TTS 调用封装，准备放入线程池
    def sync_tts(text):
        return SpeechSynthesizer.call(model='sambert-zhichu-v1', format='pcm', sample_rate=16000, text=text)

    async def process_ai_queue():
        """后台独立协程：排队处理每一句话"""
        while True:
            q_text = await task_queue.get()
            print(f"\n🗣️ 捕获完整指令: {q_text}")
            
            ai_obj = await get_ai_reply(q_text)
            diag_txt = ai_obj.get("diagnosis", "未识别")
            act_txt = ai_obj.get("action", "无")

            if act_txt != "无":
                full_voice_txt = f"{diag_txt}。执行动作：{act_txt}"
            else:
                full_voice_txt = diag_txt

            print(f"🤖 播报内容: {full_voice_txt}")

            # 【核心修复】：在线程池中运行 TTS，绝对不阻塞主事件循环！
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

    # 启动后台 AI 处理协程
    ai_task = asyncio.create_task(process_ai_queue())

    try:
        # 疯狂接收音频流，保持连接永不断开
        while True:
            raw_data = await websocket.receive_text()
            packets = raw_data.strip().split('\n')
            
            for packet in packets:
                if not packet.strip(): continue
                try:
                    msg = json.loads(packet)
                    audio_b64 = msg.get("data", {}).get("audio", "")
                    if audio_b64:
                        reg.send_audio_frame(base64.b64decode(audio_b64))
                except Exception as e: 
                    print(f"\n⚠️ 帧数据处理异常: {e}")
                
    except WebSocketDisconnect:
        print("\n❌ 客户端断开")
    finally:
        reg.stop()
        ai_task.cancel() # 清理协程

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
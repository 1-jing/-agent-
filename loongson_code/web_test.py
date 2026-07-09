import asyncio
import websockets
import os
from openai import AsyncOpenAI
# 导入 RAG 必备的组件
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import CharacterTextSplitter

# ==========================================
# 1. 基础配置与 AI 密钥
# ==========================================
API_KEY = "sk-78e5c82af1384a5793c6eb4434f87744" 
os.environ["DASHSCOPE_API_KEY"] = API_KEY

client = AsyncOpenAI(
    api_key=API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# ==========================================
# 2. 初始化 RAG 本地知识库 
# ==========================================
print("🔄 正在加载本地工艺知识库...")
try:
    loader = TextLoader("knowledge.txt", encoding="utf-8")
    docs = loader.load()
    text_splitter = CharacterTextSplitter(chunk_size=100, chunk_overlap=20, separator="\n")
    split_docs = text_splitter.split_documents(docs)
    embeddings = DashScopeEmbeddings(model="text-embedding-v1")
    vector_db = FAISS.from_documents(split_docs, embeddings)
    print("✅ 知识库加载完成，随时可以进行工艺检索！")
except Exception as e:
    print(f"❌ 知识库加载失败: {e}")
    vector_db = None

# ==========================================
# 3. 增强版大模型调用函数 (带检索功能)
# ==========================================
async def get_ai_reply(question: str) -> str:
    print(f"\n🔍 [RAG检索] 正在寻找与“{question}”相关的规程...")
    reference_context = "暂无相关参考规程"
    
    if vector_db:
        similar_docs = vector_db.similarity_search(question, k=1)
        if similar_docs:
            reference_context = similar_docs[0].page_content
            print(f"📖 [RAG命中] {reference_context.strip()}")

    system_prompt = f"""你是一个底层工业控制引擎。请严格根据现场情况和【工艺参考】给出诊断并下达硬件动作指令。
【工艺参考】：{reference_context}

【最高指令】：你必须且只能返回一个合法的 JSON 字符串，绝对不能包含任何其他说明文字，不能有Markdown标记！
【JSON格式要求】：
{{
  "diagnosis": "简短的中文诊断说明",
  "action": "必须严格按照工艺参考中的括号指令输出，如 pump_water_on 等，若无异常则输出 none"
}}"""

    try:
        response = await client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        return f'{{"diagnosis": "接口请求异常: {str(e)}", "action": "none"}}'

# ==========================================
# 4. 主动连接龙芯板子并通信
# ==========================================
async def connect_to_board():
    
    board_ip = "192.168.43.18"  # <--- 修改为龙芯板子的实际 IP
    uri = f"ws://{board_ip}:8765" 
    
    print(f"🚀 准备连接边缘硬件设备: {uri} ...")
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ 成功连上龙芯板子！开始监听传感器数据...")
            
            while True:
                # 1. 接收板子发来的传感器数据
                data = await websocket.recv()
                print(f"\n📥 [收到前端传感器数据]：{data}")
                
                # 2. 调用 AI 大脑处理数据
                ai_answer = await get_ai_reply(data)
                
                # 3. 将 JSON 动作指令发回给板子
                await websocket.send(ai_answer)
                print(f"📤 [已下发控制 JSON]：{ai_answer}")
                
    except Exception as e:
        print(f"❌ 连接断开或失败: {e}")

if __name__ == "__main__":
    asyncio.run(connect_to_board())
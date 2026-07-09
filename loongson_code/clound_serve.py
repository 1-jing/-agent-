import asyncio
import websockets
import json
import requests

# 这里以调用某个通用的大语言模型 API 为例（需替换为你申请的 API Key 和地址）
def call_llm(board_data):
    api_key = "sk-78e5c82af1384a5793c6eb4434f87744"
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 将板子传来的数据融入提示词
    prompt = f"你是一个物联网数据分析专家。这是边缘设备上传的数据：{board_data}。请简短分析并给出一条控制建议。"
    
    payload = {
        "model": "your-model-name",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        return f"云端大模型调用失败: {str(e)}"

# 处理板子连接的逻辑
async def handle_board(websocket, path):
    print("⚡ 边缘设备（龙芯板子）已连接！")
    try:
        async for message in websocket:
            print(f"📥 收到板子数据: {message}")
            
            # 拿到数据后，调用大模型
            print("🧠 正在请求大模型分析...")
            llm_reply = call_llm(message)
            
            # 将大模型的分析结果发回给板子
            await websocket.send(llm_reply)
            print(f"📤 已将 AI 分析结果返回给板子: {llm_reply}")
            
    except websockets.exceptions.ConnectionClosed:
        print("❌ 板子已断开连接")

# 启动云端 WebSocket 服务，监听所有 IP 的 8765 端口
start_server = websockets.serve(handle_board, "0.0.0.0", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
print("☁️ 云端服务已启动，等待板子上传数据...")
asyncio.get_event_loop().run_forever()
import sqlite3
import time
import requests
import json

# ================= 配置区 =================
DB_FILE = 'ferment_twin.db'
# 这里填入你的云端接收接口 (如果你自己写了后端，就填后端的 IP)
# 为了立刻测试，你可以先去 https://webhook.site/ 申请一个免费的测试 URL 填在这里
CLOUD_API_URL = 'http://你的云端服务器IP:端口/api/upload' 
SYNC_INTERVAL = 30  # 每 30 秒检查一次是否有新数据要上传
BATCH_SIZE = 50     # 每次最多打包 50 条数据发送 (防止包太大)
# ==========================================

def get_unsynced_data(cursor):
    """从数据库捞出所有还没上云的数据 (is_synced = 0)"""
    cursor.execute(f"SELECT * FROM sensor_logs WHERE is_synced = 0 LIMIT {BATCH_SIZE}")
    rows = cursor.fetchall()
    
    # 获取列名，方便组装成 JSON 字典
    columns = [description[0] for description in cursor.description]
    
    data_list = []
    for row in rows:
        data_dict = dict(zip(columns, row))
        data_list.append(data_dict)
        
    return data_list

def mark_as_synced(conn, cursor, data_list):
    """上传成功后，把这批数据的 is_synced 改为 1"""
    if not data_list: return
    
    # 提取这批数据的 ID 列表
    ids = [str(item['id']) for item in data_list]
    id_list_str = ','.join(ids)
    
    # 批量更新状态
    cursor.execute(f"UPDATE sensor_logs SET is_synced = 1 WHERE id IN ({id_list_str})")
    conn.commit()

def main():
    print(f"☁️ 数字孪生云端同步进程已启动...")
    print(f"📡 目标接口: {CLOUD_API_URL}")
    
    while True:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            # 1. 捞取数据
            payload = get_unsynced_data(cursor)
            
            if payload:
                print(f"📦 发现 {len(payload)} 条未同步数据，正在上传...")
                
                # 2. 发送给云端 (附带 JSON 格式头)
                headers = {'Content-Type': 'application/json'}
                response = requests.post(CLOUD_API_URL, data=json.dumps(payload), headers=headers, timeout=10)
                
                # 3. 如果云端返回 200 OK，说明接收成功
                if response.status_code == 200:
                    mark_as_synced(conn, cursor, payload)
                    print(f"✅ 上传成功！本地标记已更新。")
                else:
                    print(f"⚠️ 云端返回错误码: {response.status_code}，将在下个周期重试。")
            
            conn.close()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络连接失败 (可能断网了): {e} | 数据安全保留在本地。")
        except Exception as e:
            print(f"❌ 发生未知错误: {e}")
            
        # 休息 30 秒再查
        time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    main()
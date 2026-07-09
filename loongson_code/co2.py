import os
import time

def read_co2_raw(shared_data, port_name='/dev/ttyS1'):
    """
    后台死循环读取 CO2 数据，并实时更新到 shared_data 字典中
    """
    # 1. 配置串口
    os.system(f"stty -F {port_name} 9600 raw -echo")
    
    try:
        with open(port_name, 'rb', buffering=0) as ser:
            while True:
                byte = ser.read(1)
                if byte == b'\x2c':
                    data = ser.read(4)
                    if len(data) >= 2:
                        # 计算浓度
                        co2_ppm = (data[0] * 256) + data[1]
                        
                        # ★ 核心：把算出来的值塞进别人传进来的字典里
                        shared_data["co2_ppm"] = co2_ppm
                        
    except Exception as e:
        print(f"CO2 读取异常: {e}")

# ==========================================
# 独立测试逻辑（只有直接运行 python3 co2.py 时才会执行）
# ==========================================
if __name__ == "__main__":
    import threading
    
    print("💨 CO2 模块独立测试启动...")
    
    # 1. 自己造一个临时的“测试字典”
    test_dict = {"co2_ppm": 0}
    
    # 2. 开启子线程去读串口，把测试字典传给它
    threading.Thread(
        target=read_co2_raw, 
        args=(test_dict, '/dev/ttyS1'), 
        daemon=True
    ).start()
    
    # 3. 主线程在这里疯狂打印字典里的值，看看有没有被子线程更新
    try:
        while True:
            print(f"🧪 实时 CO2 浓度: {test_dict['co2_ppm']} PPM       ", end='\r')
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n测试结束，安全退出。")
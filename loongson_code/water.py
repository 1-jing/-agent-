import os
import time

# 配置
I2C_BUS = 1
ADS_ADDR = "0x48"
# 16位下的新阈值 (对应你 Arduino 代码里的 400, 600, 625, 650)
THRESHOLDS = [8000, 11200, 13000, 14500] 

def get_ads_raw():
    try:
        # 启动转换 (量程 4.096V)
        os.system(f"i2cset -y {I2C_BUS} {ADS_ADDR} 0x01 0x83C3 w > /dev/null 2>&1")
        time.sleep(0.02)
        # 读取 16 位 Word 数据
        res = os.popen(f"i2cget -y {I2C_BUS} {ADS_ADDR} 0x00 w").read().strip()
        if not res.startswith("0x"): return None
        
        val = int(res, 16)
        # 核心：大小端字节翻转 (LSB/MSB 互换)
        raw = ((val & 0xFF) << 8) | ((val >> 8) & 0xFF)
        if raw > 32767: raw -= 65536
        return raw
    except:
        return None


def read_water():
    """供外部调用的主函数，返回 裸值, 电压, 等级"""
    raw = get_ads_raw()
    
    # 如果读取失败，返回安全的默认值
    if raw is None: 
        return 0, 0.0, 0
        
    level = 0
    for t in THRESHOLDS:
        if raw > t:
            level += 1
            
    # 计算电压
    voltage = raw * (4.096 / 32767.0)
    
    # 同时返回三个数据
    return raw, voltage, level

# ==========================================
# 独立测试逻辑（只有直接运行 water.py 时才会执行）
# ==========================================
if __name__ == "__main__":
    print(" 水位模块独立测试启动...")
    while True:
        # 接收三个返回值
        r, v, lv = read_water()
        led_display = "● " * lv + "○ " * (4 - lv)
        print(f"裸值: {r:5d} | 电压: {v:.3f}V | 等级: {lv}/4 | 指示灯: {led_display}", end='\r')
        time.sleep(0.5)
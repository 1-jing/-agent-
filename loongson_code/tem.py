import os
import time
import math

# ================= 硬件配置 =================
I2C_BUS = 1           # I2C总线号
ADS_ADDR = "0x48"     # ADS1115 I2C地址

# NTC 测温电路参数
V_IN = 3.3            # 供电电压 (连接到 NTC 分压电路的电压)
R_FIXED = 10000.0     # 串联的固定分压电阻 (10kΩ)
R25 = 5000.0         # NTC 在 25°C 时的阻值 (10kΩ)
BETA = 3950.0         # NTC 的 Beta 值 (通常为 3950 或 3435)
T0 = 298.15           # 25°C 的开尔文温度
# ============================================

def get_a2_raw():
    """专门读取 ADS1115 A2 通道的原始数据"""
    try:
        # 🌟 核心修改点：0x83E3 代表选中 A2 通道与 GND 进行单端测量，量程 4.096V
        os.system(f"i2cset -y {I2C_BUS} {ADS_ADDR} 0x01 0x83E3 w > /dev/null 2>&1")
        
        # 等待 20ms 确保芯片完成模数转换
        time.sleep(0.02)
        
        # 读取 16 位 Word 数据
        res = os.popen(f"i2cget -y {I2C_BUS} {ADS_ADDR} 0x00 w").read().strip()
        if not res.startswith("0x"): 
            return None
        
        val = int(res, 16)
        
        # 完美的大小端字节翻转 (LSB/MSB 互换)
        raw = ((val & 0xFF) << 8) | ((val >> 8) & 0xFF)
        
        # 处理负数 (最高位是符号位)
        if raw > 32767: 
            raw -= 65536
            
        return raw
    except Exception as e:
        return None

def read_temperature():
    """获取并在底层换算为摄氏温度"""
    raw = get_a2_raw()
    
    # 如果读取失败，或者 raw 值异常（开路或短路），返回 None
    if raw is None or raw <= 0: 
        return None
        
    # 1. 算出 A2 引脚的真实电压 (量程 4.096V)
    voltage = raw * (4.096 / 32767.0)
    
    try:
        # 2. 精准计算 NTC 当前阻值 
        # (假设标准电路: 3.3V --- 10k电阻 --- [A2测量点] --- NTC --- GND)
        ntc_r = (voltage * R_FIXED) / (V_IN - voltage)
        
        # 3. 套用 Steinhart-Hart (Beta) 公式换算为摄氏度
        temp_k = 1.0 / ( (1.0 / T0) + (math.log(ntc_r / R25) / BETA) )
        temp_c = temp_k - 273.15
        
        return round(temp_c, 2)
        
    except (ValueError, ZeroDivisionError):
        # 防止除以零或对数计算出错
        return None

# ================= 独立测试逻辑 =================
if __name__ == "__main__":

    
    while True:
        temp = read_temperature()
        raw_val = get_a2_raw()
        
        if temp is not None and raw_val is not None:
            # 顺便把电压也算出来展示，方便底层排错
            v = raw_val * (4.096 / 32767.0)
            print(f"底层裸值: {raw_val:5d} | 电压: {v:.3f}V | 🔥 当前温度: {temp} °C    ", end='\r')
        else:
            print("❌ 读取失败，请检查接线或 I2C 地址！                ", end='\r')
            
        time.sleep(0.5)
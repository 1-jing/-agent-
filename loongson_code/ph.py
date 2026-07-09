import os
import time

# ==========================================
# ⚙️ 第一部分：硬件与 pH 校准配置
# ==========================================
I2C_BUS = 1
ADS_ADDR = "0x48"

# 复刻 Arduino 代码中的校准参数 (单位: mV) 
VOTAGE_4_0   = 2440    # pH 4.0 时的电压
VOTAGE_6_86  = 2000    # pH 6.86 时的电压，调校 Po 为 2.0V
VOTAGE_9_18  = 1600    # pH 9.18 时的电压

# ==========================================
# 🛠️ 第二部分：底层硬件驱动
# ==========================================

def get_ads_raw_a1():
    """读取 ADS1115 A1 引脚的原始 16 位数据 (量程 4.096V)"""
    # 配置字拆解：
    # MSB: 1(启动) | 101(A1-GND) | 001(4.096V量程) | 1(单次模式) = 0xD3 [cite: 1480, 1491]
    # LSB: 100(128SPS) | 00011(禁用比较器) = 0x83 [cite: 1491]
    # 由于龙芯 i2cset w 模式字节翻转，指令写为 0x83D3
    try:
        os.system(f"i2cset -y {I2C_BUS} {ADS_ADDR} 0x01 0x83D3 w > /dev/null 2>&1")
        time.sleep(0.02) # 等待转换完成 [cite: 1043]
        
        # 读取 16 位 Word 数据 (小端序 0x[LSB][MSB])
        res = os.popen(f"i2cget -y {I2C_BUS} {ADS_ADDR} 0x00 w").read().strip()
        if not res.startswith("0x"): return None
        
        val = int(res, 16)
        # 字节序翻转还原真实大端数据 [cite: 1240]
        raw = ((val & 0xFF) << 8) | ((val >> 8) & 0xFF)
        if raw > 32767: raw -= 65536 # 处理补码 [cite: 1460]
        return raw
    except:
        return None

# ==========================================
# 🧠 第三部分：pH 计算核心算法
# ==========================================

def read_ph_value(samples=20):
    """
    采集多次数据，排序后取中值平均 (复刻 Arduino 滤波逻辑) 
    """
    buf = []
    for _ in range(samples):
        r = get_ads_raw_a1()
        if r is not None:
            buf.append(r)
        time.sleep(0.01)

    if len(buf) < 10: return None, None
    
    # 1. 排序
    buf.sort()
    
    # 2. 去头去尾取平均 (去掉最高和最低的 20% 数据) 
    cut = int(len(buf) * 0.2)
    trimmed_buf = buf[cut:-cut]
    avg_raw = sum(trimmed_buf) / len(trimmed_buf)
    
    # 3. 计算电压 (mV) - 基于 4.096V 量程 [cite: 1022]
    ph_voltage_mv = avg_raw * (4096.0 / 32767.0)
    
    # 4. 分段线性计算逻辑 
    if ph_voltage_mv < VOTAGE_6_86:
        # 大于 pH 6.86 的碱性段 (电压越小，pH 越高)
        k1 = 100 * (9.18 - 6.86) / (VOTAGE_6_86 - VOTAGE_9_18)
        ph_val = (VOTAGE_6_86 - ph_voltage_mv) * k1 + 686
    else:
        # 小于等于 pH 6.86 的酸性段 (电压越大，pH 越低)
        k2 = 100 * (6.86 - 4.0) / (VOTAGE_4_0 - VOTAGE_6_86)
        ph_val = 686 - (ph_voltage_mv - VOTAGE_6_86) * k2
        
    # 5. 数值约束与转换 
    ph_val = max(0, min(1400, ph_val)) / 100.0
    
    return ph_val, ph_voltage_mv

# ==========================================
# 📊 第四部分：主循环显示
# ==========================================

if __name__ == "__main__":
    print("---------------------------------------")
    print("🧪 龙芯 pH 值实时监控系统已启动")
    print("   通道: ADS1115 A1 (Po) | 量程: 4.096V")
    print("---------------------------------------")

    try:
        while True:
            ph, mv = read_ph_value()
            if ph is not None:
                # 判定酸碱性状态
                status = "中性"
                if ph < 6.5: status = "偏酸"
                elif ph > 7.5: status = "偏碱"
                
                print(f" 当前 pH 值: {ph:.2f} |  探头电压: {mv:.1f} mV | 状态: {status}      ", end='\r')
            else:
                print("读取失败，请检查 pH 模块接线！", end='\r')
                
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n停止监测，已安全退出。")
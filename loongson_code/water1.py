import os
import time

# I2C 底层配置
I2C_BUS = 1
ADS1115_ADDR = "0x48"

def read_ads1115_a0(samples=5):
    """
    带均值滤波的水位读取函数
    :param samples: 连续读取的次数，默认 5 次。次数越多越平滑，但耗时越长。
    """
    total_raw = 0
    valid_samples = 0
    
    for _ in range(samples):
        try:
            # 1. 配置 ADS1115 寄存器 (启动单次转换)
            config_cmd = f"i2cset -y {I2C_BUS} {ADS1115_ADDR} 0x01 0x83C1 w"
            os.system(config_cmd)
            
            # 等待转换完成 (128SPS 大约需要 8ms，我们给 20ms 保底)
            time.sleep(0.02)
            
            # 2. 读取 0x00 转换结果寄存器
            read_cmd = f"i2cget -y {I2C_BUS} {ADS1115_ADDR} 0x00 w"
            result = os.popen(read_cmd).read().strip()
            
            # 如果读取失败，跳过本次采样，继续下一次
            if not result.startswith("0x"):
                continue
                
            # 3. 数据解析与高低位翻转
            hex_val = int(result, 16)
            lsb = hex_val & 0xFF
            msb = (hex_val >> 8) & 0xFF
            
            # 重新拼装成正确的 16 位整数
            raw_val = (msb << 8) | lsb
            
            # 4. 处理符号位 (超过 32767 为负数)
            if raw_val > 32767:
                raw_val -= 65536
                
            # 【新增特性 1】软件底噪截断：如果算出负数，强制归零
            if raw_val < 0:
                raw_val = 0
                
            # 累加有效数据
            total_raw += raw_val
            valid_samples += 1

        except Exception as e:
            # 单次异常不中断整个程序，直接跳过
            continue

    # 5. 计算平均值与真实电压
    if valid_samples > 0:
        avg_raw = int(total_raw / valid_samples)
        
        # 保持你的修正点：使用 4.096V 量程
        avg_voltage = avg_raw * (4.096 / 32767.0) 
        
        return avg_raw, avg_voltage
    else:
        return None, None

if __name__ == "__main__":
    print("🌊 高精度水位传感器 (均值滤波 + 底噪归零版)...")
    print("您可以把传感器放进水里，观察跳变是否消失！\n")
    
    try:
        while True:
            # 调用时执行 5 次连续采样求平均
            raw, volts = read_ads1115_a0(samples=5)
            
            if raw is not None:
                # 打印原始值和计算出的真实电压
                print(f"💧 16位高精度裸值: {raw:5d}  |  ⚡ 实际电压: {volts:.3f} V", end='\r')
            else:
                print("⚠️ 读取失败，请检查接线。", end='\r')
                
            # 因为函数内部 5 次采样本身要消耗大约 0.1 秒，外层的 sleep 可以稍微缩短
            time.sleep(0.4)
            
    except KeyboardInterrupt:
        print("\n\n测试结束，安全退出。")
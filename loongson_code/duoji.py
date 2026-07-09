import os
import time

class PWMController:
    def __init__(self, pwmchip=0, channel=0):
        """初始化PWM控制器"""
        self.pwmchip = pwmchip
        self.channel = channel
        self.base_path = f"/sys/class/pwm/pwmchip{self.pwmchip}"
        self.pwm_path = f"{self.base_path}/pwm{self.channel}"
        
        # 检查PWM芯片是否存在
        if not os.path.exists(self.base_path):
            raise FileNotFoundError(f"PWM芯片 {self.pwmchip} 不存在")
    
    def export(self):
        """导出PWM通道"""
        if not os.path.exists(self.pwm_path):
            try:
                with open(f"{self.base_path}/export", "w") as f:
                    f.write(str(self.channel))
                time.sleep(0.1)  # 等待系统创建文件
            except Exception as e:
                raise RuntimeError(f"无法导出PWM通道 {self.channel}: {e}")
    
    def unexport(self):
        """取消导出PWM通道"""
        if os.path.exists(self.pwm_path):
            try:
                with open(f"{self.base_path}/unexport", "w") as f:
                    f.write(str(self.channel))
            except Exception as e:
                raise RuntimeError(f"无法取消导出PWM通道 {self.channel}: {e}")
    
    def enable(self):
        """启用PWM输出"""
        self._write_value("enable", "1")
    
    def disable(self):
        """禁用PWM输出"""
        self._write_value("enable", "0")
    
    def set_period(self, period_ns):
        """设置PWM周期(纳秒)"""
        self._write_value("period", str(int(period_ns)))
    
    def set_duty_cycle(self, duty_ns):
        """设置PWM占空时间(纳秒)"""
        self._write_value("duty_cycle", str(int(duty_ns)))
    
    def set_frequency(self, frequency_hz):
        """设置PWM频率(Hz)"""
        period_ns = int(1e9 / frequency_hz)
        self.set_period(period_ns)
    
    def _write_value(self, filename, value):
        """写入值到PWM文件"""
        try:
            with open(f"{self.pwm_path}/{filename}", "w") as f:
                f.write(value)
        except Exception as e:
            raise RuntimeError(f"无法写入 {filename}: {e}")


class ServoController(PWMController):
    """
    舵机专属控制器，继承自 PWMController
    默认使用 pwmchip2, channel 0
    """
    def __init__(self, pwmchip=2, channel=0):
        # 调用父类初始化
        super().__init__(pwmchip, channel)
        
        # 舵机的物理常数
        self.SERVO_FREQ = 50           # 舵机标准频率 50Hz
        self.MIN_DUTY_NS = 500000      # 0度 对应的脉宽 0.5ms (500,000 ns)
        self.MAX_DUTY_NS = 2500000     # 180度 对应的脉宽 2.5ms (2,500,000 ns)
        
    def setup(self):
        """初始化舵机工作环境"""
        self.export()
        
        # ⚠️ 关键顺序：必须先设置周期，再设置占空比，否则 Linux 底层会报错 (duty_cycle 不能大于 period)
        self.set_frequency(self.SERVO_FREQ) 
        
        # 默认停在90度中位
        self.set_angle(90)
        self.enable()
        print(f"舵机已在 pwmchip{self.pwmchip}-pwm{self.channel} 上初始化，默认归位90度。")
    def set_angle(self, angle):
            """
            输入 0~180 度的角度，自动计算并设置 PWM 占空比
            （已加入反相适配逻辑）
            """
            # 限制角度范围，防止烧毁舵机
            if angle < 0: angle = 0
            if angle > 180: angle = 180
            
            # 1. 先计算正常情况下的脉宽 (0度=0.5ms, 180度=2.5ms)
            duty_ns = self.MIN_DUTY_NS + (self.MAX_DUTY_NS - self.MIN_DUTY_NS) * (angle / 180.0)
            
            # 2. 【核心黑魔法】：因为板子硬件输出了反相信号，我们用总周期减去正常脉宽
            # 总周期是 20ms，也就是 20000000 ns
            inverted_duty_ns = 20000000 - duty_ns
            
            # 3. 把反转后的数值写进去
            self.set_duty_cycle(inverted_duty_ns)
            print(f" -> 执行动作: 舵机转至 {angle}° (实际写入底层脉宽: {int(inverted_duty_ns)} ns)")
    

# ================= 使用示例 =================
# ================= 交互式调试工具 =================
if __name__ == "__main__":
    # 实例化舵机控制器 (目标: chip2, pwm0)
    servo = ServoController(pwmchip=2, channel=0)
    
    try:
        # 初始化并通电
        servo.setup()
        print("\n=======================================")
        print("💡 交互调试模式已开启！(此时板子上的 LED 应该长亮或微弱闪烁)")
        print("现在系统会持续输出 PWM 信号，你可以放心排查硬件连线了。")
        print("请输入 0 到 180 之间的数字来转动舵机。")
        print("输入 'q' 退出并释放资源。")
        print("=======================================\n")
        
        while True:
            cmd = input("👉 请输入目标角度 (0-180) / q 退出: ")
            
            if cmd.lower() == 'q':
                break
                
            try:
                angle = float(cmd)
                servo.set_angle(angle)
            except ValueError:
                print("❌ 格式错误：请输入数字或 'q'")
                
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，准备退出...")
    except Exception as e:
        print(f"发生错误: {e}")
        
    finally:
        # 安全退出，释放资源
        print("\n正在释放系统资源...")
        try:
            servo.disable()
            servo.unexport()
            print("资源已安全释放，PWM 通道已关闭。")
        except Exception as e:
            print(f"释放资源时出错: {e}")

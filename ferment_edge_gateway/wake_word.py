import subprocess
import os
import sys
from config import SHERPA_CMD, SHERPA_ROOT

def wait_for_wake_word():
    """阻塞型函数：死盯麦克风，直到听见唤醒词才放行"""
    print("\n" + "="*50)
    print("💤 [状态：待机] 启动离线神经引擎，请说话...")
    
    env = os.environ.copy()
    # 核心修改：让程序去资源文件夹里寻找必要的动态库 (.so文件)
    env["LD_LIBRARY_PATH"] = f"{SHERPA_ROOT}:{env.get('LD_LIBRARY_PATH', '')}"
    env["ALSA_CONFIG_DIR"] = "/usr/share/alsa"
    
    # 核心修改：增加 cwd 参数，让引擎在模型所在的文件夹下运行
    process = subprocess.Popen(
        SHERPA_CMD, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True, 
        env=env, 
        bufsize=1,
        cwd=SHERPA_ROOT  
    )
    
    buffer = ""
    try:
        while True:
            char = process.stdout.read(1) 
            if not char: break
            
            # 实时打印识别到的字到终端
            sys.stdout.write(char)
            sys.stdout.flush()
            
            buffer += char
            
            # 唤醒词容错字典
            wake_words = ["小龙小龙","把龙小龙","小楼小楼","老龙小龙","小龙嫂龙"]
            
            if any(word in buffer for word in wake_words):
                print("\n\n✨ [触发！] 命中唤醒词，正在移交系统控制权...")
                break 
                
            if char in ['\n', '\r']:
                buffer = ""
                
    finally:
        # 释放资源
        process.terminate()
        process.wait()
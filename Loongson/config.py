# ================= 硬件串口配置 (与久久派通信) =================
# 根据实际使用的串口节点进行修改（可能需要 sudo chmod 666 /dev/ttyS1 赋权）
SERIAL_PORT = "/dev/ttyS3"  
SERIAL_BAUDRATE = 9600
# ================= 网络配置 =================
#10.218.235.131 
SERVER_IP = "192.168.222.131"  
WS_URL = f"ws://{SERVER_IP}:8000/ws/voice_device"

MQTT_BROKER = SERVER_IP
MQTT_PORT = 1883
MQTT_TOPIC = "fermenter/2kla10000/telemetry"
MQTT_INTERVAL = 5.0  

# ================= 音频硬件配置 =================
DEVICE = "plughw:1,0"
SAMPLE_RATE = 16000
CHUNK_SIZE = 3200
REPLY_AUDIO = "server_reply.wav"

# ================= 唤醒引擎配置 =================
IDLE_TIMEOUT = 90.0 

# --- 定义 sherpa 资源所在的绝对路径 ---
# 注意：~ 在代码中建议写成完整的 /home/loongson
SHERPA_ROOT = "/home/loongson/sherpa-ncnn-streaming-zipformer-zh-14M-2023-02-23"

# 使用绝对路径重组命令
SHERPA_CMD = [
    "stdbuf", "-o0",  
    f"{SHERPA_ROOT}/sherpa-ncnn-alsa", 
    f"{SHERPA_ROOT}/tokens.txt",
    f"{SHERPA_ROOT}/encoder_jit_trace-pnnx.ncnn.param", 
    f"{SHERPA_ROOT}/encoder_jit_trace-pnnx.ncnn.bin",
    f"{SHERPA_ROOT}/decoder_jit_trace-pnnx.ncnn.param", 
    f"{SHERPA_ROOT}/decoder_jit_trace-pnnx.ncnn.bin",
    f"{SHERPA_ROOT}/joiner_jit_trace-pnnx.ncnn.param", 
    f"{SHERPA_ROOT}/joiner_jit_trace-pnnx.ncnn.bin",
    DEVICE
]
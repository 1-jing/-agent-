# audio_service.py
# 龙芯 2K1000LA 本机智能服务端音频模块
# 功能：
# 1. DashScope ASR 回调
# 2. DashScope TTS 合成
# 3. TTS 失败时不抛异常，避免 WebSocket 主流程崩溃
# 4. 修正小数、百分号、比较符号的播报问题

import os
import re
import time
import dashscope
from dashscope.audio.asr import RecognitionCallback, RecognitionResult
from dashscope.audio.tts import SpeechSynthesizer


# 从环境变量读取 API Key
_api_key = os.environ.get("DASHSCOPE_API_KEY", "")
if _api_key:
    dashscope.api_key = _api_key
else:
    print("⚠️ [audio_service] 未设置 DASHSCOPE_API_KEY，ASR/TTS 可能无法使用")


class MyASRCallback(RecognitionCallback):
    def __init__(self):
        self.text = ""

    def on_event(self, result: RecognitionResult):
        try:
            sent = result.get_sentence()
            if sent and result.is_sentence_end(sent):
                self.text = sent.get("text", "")
        except Exception as e:
            print("⚠️ [ASR回调] 解析异常:", e)


def digit_to_cn(s: str) -> str:
    """
    把小数部分逐位读出来：
    66 -> 六六
    0352 -> 零三五二
    """
    table = {
        "0": "零",
        "1": "一",
        "2": "二",
        "3": "三",
        "4": "四",
        "5": "五",
        "6": "六",
        "7": "七",
        "8": "八",
        "9": "九",
    }
    return "".join(table.get(ch, ch) for ch in s)


def normalize_tts_text(text: str) -> str:
    """
    TTS 播报文本归一化：
    5.5-6.2 -> 5点五到6点二
    11.66 -> 11点六六
    0.0352 -> 0点零三五二
    > -> 大于
    < -> 小于
    """
    speak_text = str(text or "")

    # 1. 数字范围必须最先处理，否则 5.5-6.2 会先变成 5点五-6点二，后面就不好识别了
    # 支持：5.5-6.2、5.5－6.2、5.5–6.2、5.5—6.2、5.5−6.2、5.5~6.2、5.5～6.2
    speak_text = re.sub(
        r'(\d+(?:\.\d+)?)\s*[-－–—−~～]\s*(\d+(?:\.\d+)?)',
        r'\1到\2',
        speak_text
    )

    # 2. 比较符号
    speak_text = speak_text.replace(">=", "大于等于")
    speak_text = speak_text.replace("<=", "小于等于")
    speak_text = speak_text.replace("≥", "大于等于")
    speak_text = speak_text.replace("≤", "小于等于")
    speak_text = speak_text.replace(">", "大于")
    speak_text = speak_text.replace("<", "小于")

    # 3. 专业词
    speak_text = speak_text.replace("CO2", "二氧化碳").replace("co2", "二氧化碳")
    speak_text = speak_text.replace("pH", "P H ").replace("PH", "P H ")

    # 4. 百分号：3.5% -> 百分之3.5
    speak_text = re.sub(r'([0-9]+(?:\.[0-9]+)?)%', r'百分之\1', speak_text)

    # 5. 小数点逐位读：5.5 -> 5点五；6.2 -> 6点二；11.66 -> 11点六六
    def decimal_repl(m):
        int_part = m.group(1)
        dec_part = m.group(2)
        return int_part + "点" + digit_to_cn(dec_part)

    speak_text = re.sub(r'(\d+)\.(\d+)', decimal_repl, speak_text)

    # 6. 避免单独的 2 被读成“两”
    speak_text = re.sub(r'(?<!\d)2(?!\d)', '二', speak_text)

    return speak_text


def get_tts_audio(text: str) -> bytes:
    """
    调用阿里 DashScope TTS。

    重要：
    这个函数会被 main.py 放到线程池中执行，
    避免 DashScope TTS 内部事件循环和 FastAPI WebSocket 的事件循环冲突。

    返回：
    成功：PCM bytes
    失败：b""
    """
    speak_text = normalize_tts_text(text)

    if not speak_text.strip():
        print("⚠️ [TTS] 空文本，跳过合成")
        return b""

    print(f"🎙️ [播音底稿修正]: {speak_text}")

    for attempt in range(2):
        try:
            # 确保线程里也能拿到 API Key
            api_key = os.environ.get("DASHSCOPE_API_KEY", "")
            if api_key:
                dashscope.api_key = api_key

            tts = SpeechSynthesizer.call(
                model='sambert-zhichu-v1',
                format='pcm',
                sample_rate=16000,
                text=speak_text
            )

            audio = None

            if hasattr(tts, "get_audio_data"):
                audio = tts.get_audio_data()
            elif isinstance(tts, (bytes, bytearray)):
                audio = tts

            if audio:
                return audio

            print("⚠️ [TTS] 未获取到音频数据，attempt =", attempt + 1)

        except Exception as e:
            print("❌ [TTS] 合成异常 attempt=%d，不中断主流程: %s" % (attempt + 1, e))

        time.sleep(0.5)

    print("⚠️ [TTS] 两次合成失败，返回空音频")
    return b""
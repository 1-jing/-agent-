import asyncio
import base64
import json
import os
import subprocess
import time

import websockets

import http_receiver
from config import CHUNK_SIZE, DEVICE, IDLE_TIMEOUT, REPLY_AUDIO, SAMPLE_RATE, WS_URL


is_playing = False
last_active_time = 0.0


def play_local_audio(filename):
    if not os.path.exists(filename):
        return
    print(f"[audio] playing {filename}")
    cmd = f"env -u LD_LIBRARY_PATH -u ALSA_CONFIG_DIR aplay -D {DEVICE} {filename} > /dev/null 2>&1"
    os.system(cmd)


async def cloud_session():
    global is_playing, last_active_time
    last_active_time = time.time()

    print("[voice] starting microphone stream...")
    arecord_proc = subprocess.Popen(
        [
            "arecord",
            "-D",
            DEVICE,
            "-f",
            "S16_LE",
            "-r",
            str(SAMPLE_RATE),
            "-c",
            "1",
            "-t",
            "raw",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    try:
        async with websockets.connect(WS_URL) as ws:
            print("[voice] websocket connected")

            async def recv_task():
                nonlocal arecord_proc
                global is_playing, last_active_time

                while True:
                    raw_msg = await ws.recv()
                    res = json.loads(raw_msg)

                    text = res.get("text")
                    if text:
                        print("\n" + "=" * 50)
                        print(f"AI: {text}")

                        hw_cmd = res.get("hw_cmd", "NONE")
                        if hw_cmd != "NONE":
                            ok = http_receiver.enqueue_action(hw_cmd, source="llm")
                            if ok:
                                print(f"[action] queued cloud command -> {hw_cmd}")
                            else:
                                print(f"[action] rejected cloud command -> {hw_cmd}")

                        print("=" * 50)

                    audio_b64 = res.get("audio")
                    if audio_b64:
                        with open(REPLY_AUDIO, "wb") as f:
                            f.write(base64.b64decode(audio_b64))

                        is_playing = True
                        if arecord_proc and arecord_proc.poll() is None:
                            arecord_proc.terminate()
                            arecord_proc.wait()

                        try:
                            play_cmd = (
                                "env -u LD_LIBRARY_PATH -u ALSA_CONFIG_DIR "
                                f"aplay -D {DEVICE} -t raw -c 1 -f S16_LE -r 16000 {REPLY_AUDIO}"
                            )
                            play_proc = await asyncio.create_subprocess_shell(
                                play_cmd,
                                stdout=asyncio.subprocess.DEVNULL,
                                stderr=asyncio.subprocess.DEVNULL,
                            )
                            await asyncio.wait_for(play_proc.wait(), timeout=60.0)
                        except Exception as e:
                            print(f"[audio] playback interrupted: {e}")
                        finally:
                            is_playing = False
                            arecord_proc = subprocess.Popen(
                                [
                                    "arecord",
                                    "-D",
                                    DEVICE,
                                    "-f",
                                    "S16_LE",
                                    "-r",
                                    str(SAMPLE_RATE),
                                    "-c",
                                    "1",
                                    "-t",
                                    "raw",
                                ],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                            )
                            last_active_time = time.time()

            async def send_task():
                nonlocal arecord_proc
                global is_playing, last_active_time

                while True:
                    if time.time() - last_active_time > IDLE_TIMEOUT:
                        print(f"[voice] idle timeout after {IDLE_TIMEOUT}s")
                        return

                    if is_playing or arecord_proc is None or arecord_proc.poll() is not None:
                        await asyncio.sleep(0.1)
                        continue

                    audio_chunk = arecord_proc.stdout.read(CHUNK_SIZE)
                    if not audio_chunk:
                        await asyncio.sleep(0.1)
                        continue

                    payload = {
                        "data": {
                            "status": 1,
                            "audio": base64.b64encode(audio_chunk).decode(),
                        }
                    }
                    await ws.send(json.dumps(payload))
                    await asyncio.sleep(0.01)

            done, pending = await asyncio.wait(
                [asyncio.create_task(recv_task()), asyncio.create_task(send_task())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except websockets.exceptions.ConnectionClosed:
        print("[voice] websocket closed")
    except Exception as e:
        print(f"[voice] session error: {e}")
    finally:
        if arecord_proc and arecord_proc.poll() is None:
            arecord_proc.terminate()
            arecord_proc.wait()

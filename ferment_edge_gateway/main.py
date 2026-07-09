import asyncio
import threading
import time

import http_receiver
import mqtt_task
from audio_stream import cloud_session, play_local_audio
from wake_word import wait_for_wake_word


def init_hardware():
    print("[system] initializing Loongson edge gateway...")


def main():
    init_hardware()

    # Receive telemetry from 2K0300 over HTTP and write SQLite.
    threading.Thread(target=http_receiver.main, daemon=True).start()

    # Publish latest real SQLite telemetry to cloud/MQTT.
    threading.Thread(target=mqtt_task.mqtt_publisher_loop, daemon=True).start()

    print("[system] ready: HTTP receiver + MQTT publisher + voice assistant")

    while True:
        try:
            wait_for_wake_word()
            play_local_audio("awake_reply.wav")
            asyncio.run(cloud_session())
            play_local_audio("sleep_reply.wav")
        except KeyboardInterrupt:
            print("\n[system] stopped")
            break
        except Exception as e:
            print(f"[system] main loop error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()

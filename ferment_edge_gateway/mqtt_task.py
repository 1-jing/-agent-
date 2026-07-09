import json
import sqlite3
import time

import paho.mqtt.client as mqtt

from config import MQTT_BROKER, MQTT_INTERVAL, MQTT_PORT, MQTT_TOPIC


DB_FILE = "ferment_twin.db"
CURRENT_STAGE = "Stage 1"


def get_latest_sensor_data():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(sensor_logs)")
        columns = {row[1] for row in cursor.fetchall()}
        vent_expr = "vent_angle" if "vent_angle" in columns else "0 AS vent_angle"
        pump_expr = "pump_water_enable" if "pump_water_enable" in columns else "0 AS pump_water_enable"
        cursor.execute(
            f"""
            SELECT
                id, timestamp, batch_id,
                co2_percent, ph_val, water_raw, water_v, water_level, tem,
                motor_enable, motor_direction, motor_pwm, motor_actual_rpm,
                motor_fault, {vent_expr}, {pump_expr}, is_event, alarm_level, alarm_reason, action
            FROM sensor_logs
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.close()
    except Exception as e:
        return {
            "status": "db_error",
            "error": str(e),
            "stage": CURRENT_STAGE,
        }

    if row is None:
        return {
            "status": "waiting_for_sensor_data",
            "stage": CURRENT_STAGE,
        }

    return {
        "status": "online",
        "stage": CURRENT_STAGE,
        "id": row["id"],
        "timestamp": row["timestamp"],
        "batch_id": row["batch_id"],
        "co2_percent": row["co2_percent"],
        "ph_val": row["ph_val"],
        "water_raw": row["water_raw"],
        "water_v": row["water_v"],
        "water_level": row["water_level"],
        "temp_c": row["tem"],
        "motor_enable": row["motor_enable"],
        "motor_direction": row["motor_direction"],
        "motor_pwm": row["motor_pwm"],
        "motor_actual_rpm": row["motor_actual_rpm"],
        "motor_fault": row["motor_fault"],
        "vent_angle": row["vent_angle"],
        "pump_water_enable": row["pump_water_enable"],
        "is_event": row["is_event"],
        "alarm_level": row["alarm_level"],
        "alarm_reason": row["alarm_reason"],
        "action": row["action"],
    }


def mqtt_publisher_loop():
    client = mqtt.Client(client_id="loongson_main_gateway")
    client.will_set(MQTT_TOPIC, json.dumps({"status": "offline"}), qos=1, retain=True)

    while True:
        try:
            print(f"[MQTT] connecting to broker {MQTT_BROKER}:{MQTT_PORT}...")
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except Exception as e:
            print(f"[MQTT] connect failed, retrying in 5s: {e}")
            time.sleep(5)

    client.loop_start()
    print(f"[MQTT] publisher online, topic={MQTT_TOPIC}, stage={CURRENT_STAGE}")

    while True:
        try:
            data = get_latest_sensor_data()
            client.publish(MQTT_TOPIC, json.dumps(data, ensure_ascii=False), qos=0)
            time.sleep(MQTT_INTERVAL)
        except Exception as e:
            print(f"[MQTT] publish failed: {e}")
            time.sleep(5)

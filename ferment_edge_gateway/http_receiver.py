import json
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = 8080
DB_FILE = "ferment_twin.db"
BATCH_ID = "EXP_20260422_01"

NORMAL_SAVE_INTERVAL_S = 60
EVENT_REPEAT_INTERVAL_S = 60
MAX_ROWS = 10000

PH_LOW = 3.8
PH_HIGH = 8.8
TEMP_LOW_C = 5.0
TEMP_HIGH_C = 28.0
CO2_HIGH_PERCENT = 1.0
WATER_HIGH_LEVEL = 4

last_normal_save_time = 0.0
last_event_save_time = 0.0
last_event_reason = "none"
pending_actions = {}
latest_sensor_data = None
last_sensor_seen_ts = 0.0

DEFAULT_DEVICE_ID = "2k0300-fermenter-node"
ACTION_KEEP = "keep"
last_dispatched_action = ACTION_KEEP
last_dispatched_at = 0.0
demo_cursor = 0

MOTOR_PWM_LEVELS = {0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100}
ALLOWED_ACTIONS = {
    ACTION_KEEP,
    "motor_stop",
    "pump_water_on",
    "pump_water_off",
    "vent_open",
    "vent_close",
    "vent_mid",
}
ACTION_ALIASES = {
    "NONE": ACTION_KEEP,
    "alarm_only": ACTION_KEEP,
}

STAGE_DIAGNOSIS = {
    1: "\u542f\u52a8\u671f / \u9002\u5e94\u53d1\u9175",
    2: "\u6307\u6570\u671f / \u6d3b\u8dc3\u589e\u6b96",
    3: "\u7a33\u5b9a\u671f / \u6709\u6c27\u589e\u6b96\u671f",
    4: "\u8870\u9000\u671f / \u6d3b\u6027\u4e0b\u964d",
}


def normalize_action(action):
    action = str(action).strip()
    action = ACTION_ALIASES.get(action, action)
    if action.startswith("motor_pwm_"):
        try:
            pwm_text = action.split("_")[-1]
            pwm = int(pwm_text)
        except ValueError:
            return None
        if pwm not in MOTOR_PWM_LEVELS:
            return None
        return f"motor_pwm_{pwm}"
    if action.startswith("vent_angle_"):
        try:
            angle = int(float(action.split("_")[-1]))
        except ValueError:
            return None
        if angle < 0 or angle > 180:
            return None
        return f"vent_angle_{angle}"
    if action not in ALLOWED_ACTIONS:
        return None
    return action


def action_parts(action):
    return [
        part.strip()
        for part in str(action or "").split("|")
        if part.strip() and part.strip() not in ("none", "keep", ACTION_KEEP)
    ]


def has_hardware_action(action):
    return any(normalize_action(part) not in (None, ACTION_KEEP) for part in action_parts(action))


def enqueue_action(action, device_id=DEFAULT_DEVICE_ID, source="llm"):
    normalized = normalize_action(action)
    if normalized is None:
        print(f"[action] rejected unsupported action from {source}: {action}")
        return False
    if normalized == ACTION_KEEP:
        return True
    pending_actions[device_id] = {
        "action": normalized,
        "source": source,
        "queued_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print(f"[action] queued for {device_id}: {normalized} source={source}")
    return True


def pop_action(device_id):
    item = pending_actions.pop(device_id, None)
    if item is None:
        return {
            "action": ACTION_KEEP,
            "action_source": "none",
            "queued_at": None,
        }
    return {
        "action": item["action"],
        "action_source": item["source"],
        "queued_at": item["queued_at"],
    }


def peek_action(device_id):
    item = pending_actions.get(device_id)
    return item["action"] if item else ACTION_KEEP


def number_value(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def int_value(value, default=0):
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def stage_index_from_data(data):
    raw_stage = data.get("stage_index", data.get("stage_id", data.get("phase_index")))
    if raw_stage is not None:
        index = int_value(raw_stage, 3)
        if 1 <= index <= 4:
            return index
        return max(1, min(4, index + 1))

    co2 = number_value(data.get("co2_percent"), 0.0)
    temp = number_value(data.get("temp_c", data.get("tem")), 0.0)
    ph = number_value(data.get("ph_val"), 0.0)

    if co2 < 0.08 and temp < 20.0:
        return 1
    if co2 < 0.45:
        return 2
    if 3.8 <= ph <= 8.8 and co2 <= 1.0:
        return 3
    return 4


def recommendation_from_data(data, event_info):
    alarm_reason = event_info.get("alarm_reason", "none")
    if "motor_" in alarm_reason:
        return "\u505c\u6b62\u6405\u62cc\uff0c\u68c0\u67e5\u7535\u673a"
    if "temp_high" in alarm_reason:
        return "\u5f00\u542f\u6c34\u6cf5\uff0c\u964d\u4f4e\u6e29\u5ea6"
    if "temp_low" in alarm_reason:
        return "\u6682\u505c\u8865\u6c34\uff0c\u7b49\u5f85\u5347\u6e29"
    if "co2_high" in alarm_reason:
        return "\u589e\u52a0\u6392\u6c14\uff0c\u4fdd\u6301\u901a\u98ce"
    if "water_level_high" in alarm_reason:
        return "\u5173\u95ed\u6c34\u6cf5\uff0c\u68c0\u67e5\u6db2\u4f4d"
    if "ph_" in alarm_reason:
        return "\u7ef4\u6301\u6405\u62cc\uff0c\u590d\u6838pH"

    pwm = number_value(data.get("motor_pwm"), 0.0)
    if pwm < 30.0:
        return "\u7ef4\u6301\u4f4e\u901f\u6405\u62cc"
    if pwm > 70.0:
        return "\u964d\u4f4e\u6405\u62cc\uff0c\u4fdd\u6301\u901a\u6c14"
    return "\u7ef4\u6301\u4e2d\u901f\u6405\u62cc\uff0c\u4fdd\u6301\u901a\u6c14"


def priority_from_event(event_info):
    level = str(event_info.get("alarm_level", "normal"))
    if level == "critical":
        return "\u9ad8"
    if level == "warning":
        return "\u4e2d"
    return "\u4e2d"


def event_info_from_latest(data):
    return {
        "is_event": int_value(data.get("is_event"), 0),
        "alarm_level": str(data.get("alarm_level", "normal")),
        "alarm_reason": str(data.get("alarm_reason", "none")),
        "action": str(data.get("event_action", data.get("action", "none"))),
    }


def visible_queued_action(device_id):
    queued = peek_action(device_id)
    if queued != ACTION_KEEP:
        return queued
    if last_dispatched_action != ACTION_KEEP and time.time() - last_dispatched_at <= 30:
        return last_dispatched_action
    return ACTION_KEEP


def event_status_from_event(event_info, queued_action=ACTION_KEEP):
    if not event_info.get("is_event") or event_info.get("alarm_reason") == "none":
        return "\u5df2\u6062\u590d"

    event_action = event_info.get("action", "none")
    if has_hardware_action(event_action):
        if has_hardware_action(queued_action):
            return "\u6267\u884c\u4e2d"
        return "\u5f85\u6267\u884c"

    return "\u5f85\u5904\u7406"


def clamp_value(value, low, high):
    return max(low, min(high, value))


def enrich_latest_data(data, event_info=None):
    enriched = dict(data)
    event_info = event_info or event_info_from_latest(enriched)
    device_id = str(enriched.get("device_id", DEFAULT_DEVICE_ID))
    stage_index = stage_index_from_data(enriched)
    queued_action = visible_queued_action(device_id)
    event_action = event_info.get("action", "none")

    enriched["device_id"] = device_id
    enriched["stage_index"] = stage_index
    enriched["diagnosis"] = STAGE_DIAGNOSIS.get(stage_index, STAGE_DIAGNOSIS[3])
    enriched["recommendation"] = recommendation_from_data(enriched, event_info)
    enriched["priority"] = priority_from_event(event_info)
    enriched["event_action"] = event_action
    enriched["queued_action"] = queued_action
    enriched["event_status"] = event_status_from_event(event_info, queued_action)
    enriched["action"] = queued_action if queued_action != ACTION_KEEP else event_action
    return enriched


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            batch_id TEXT,
            co2_percent REAL,
            ph_val REAL,
            water_raw INTEGER,
            water_v REAL,
            water_level INTEGER,
            tem REAL,
            motor_enable INTEGER DEFAULT 0,
            motor_direction TEXT DEFAULT 'stop',
            motor_pwm REAL DEFAULT 0,
            motor_actual_rpm REAL DEFAULT 0,
            motor_fault TEXT DEFAULT 'none',
            vent_angle REAL DEFAULT 0,
            pump_water_enable INTEGER DEFAULT 0,
            is_event INTEGER DEFAULT 0,
            alarm_level TEXT DEFAULT 'normal',
            alarm_reason TEXT DEFAULT 'none',
            action TEXT DEFAULT 'none',
            is_synced INTEGER DEFAULT 0
        )
        """
    )
    ensure_columns(conn, cursor)
    conn.commit()
    return conn


def ensure_columns(conn, cursor):
    extra_columns = {
        "co2_percent": "REAL",
        "motor_enable": "INTEGER",
        "motor_direction": "TEXT",
        "motor_pwm": "REAL",
        "motor_actual_rpm": "REAL",
        "motor_fault": "TEXT",
        "vent_angle": "REAL DEFAULT 0",
        "pump_water_enable": "INTEGER DEFAULT 0",
        "is_event": "INTEGER DEFAULT 0",
        "alarm_level": "TEXT DEFAULT 'normal'",
        "alarm_reason": "TEXT DEFAULT 'none'",
        "action": "TEXT DEFAULT 'none'",
        "is_synced": "INTEGER DEFAULT 0",
    }
    cursor.execute("PRAGMA table_info(sensor_logs)")
    existing = {row[1] for row in cursor.fetchall()}
    for name, sql_type in extra_columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE sensor_logs ADD COLUMN {name} {sql_type}")
    conn.commit()


def normalize_payload(payload):
    return {
        "device_id": str(payload.get("device_id", DEFAULT_DEVICE_ID)),
        "co2_percent": float(payload.get("co2_percent", 0.0)),
        "ph_val": float(payload.get("ph_val", 0.0)),
        "water_raw": int(payload.get("water_raw", 0)),
        "water_v": float(payload.get("water_v", 0.0)),
        "water_level": int(payload.get("water_level", 0)),
        "tem": float(payload.get("tem", payload.get("temp_c", 0.0))),
        "motor_enable": int(payload.get("motor_enable", 0)),
        "motor_direction": str(payload.get("motor_direction", "stop")),
        "motor_pwm": float(payload.get("motor_pwm", 0.0)),
        "motor_actual_rpm": float(payload.get("motor_actual_rpm", 0.0)),
        "motor_fault": str(payload.get("motor_fault", "none")),
        "vent_angle": float(payload.get("vent_angle", 0.0)),
        "pump_water_enable": int(payload.get("pump_water_enable", 0)),
    }


def evaluate_event(data):
    reasons = []
    actions = []
    level = "normal"

    if data["ph_val"] < PH_LOW:
        reasons.append("ph_low")
        actions.append("pump_alkali_on")
        level = "warning"
    elif data["ph_val"] > PH_HIGH:
        reasons.append("ph_high")
        actions.append("check_ph_probe")
        level = "warning"

    if data["tem"] > TEMP_HIGH_C:
        reasons.append("temp_high")
        actions.append("pump_water_on")
        level = "critical"
    elif data["tem"] < TEMP_LOW_C:
        reasons.append("temp_low")
        actions.append("pump_heat_on")
        if level != "critical":
            level = "warning"

    if data["co2_percent"] > CO2_HIGH_PERCENT:
        reasons.append("co2_high")
        actions.append("check_exhaust")
        if level != "critical":
            level = "warning"

    if data["water_level"] >= WATER_HIGH_LEVEL:
        reasons.append("water_level_high")
        actions.append("pump_defoamer_on")
        level = "critical"

    if data["motor_fault"] != "none":
        reasons.append(f"motor_{data['motor_fault']}")
        actions.append("check_motor")
        if level == "normal":
            level = "warning"

    return {
        "is_event": 1 if reasons else 0,
        "alarm_level": level,
        "alarm_reason": "|".join(reasons) if reasons else "none",
        "action": "|".join(dict.fromkeys(actions)) if actions else "none",
    }


def should_save(event_info):
    global last_normal_save_time, last_event_save_time, last_event_reason

    now = time.monotonic()
    if event_info["is_event"]:
        reason = event_info["alarm_reason"]
        if reason != last_event_reason or now - last_event_save_time >= EVENT_REPEAT_INTERVAL_S:
            last_event_reason = reason
            last_event_save_time = now
            return "event"
        return None

    if now - last_normal_save_time >= NORMAL_SAVE_INTERVAL_S:
        last_normal_save_time = now
        return "normal"

    return None


def insert_row(data, event_info):
    conn = init_db()
    cursor = conn.cursor()
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO sensor_logs (
            timestamp, batch_id,
            co2_percent, ph_val, water_raw, water_v, water_level, tem,
            motor_enable, motor_direction, motor_pwm, motor_actual_rpm,
            motor_fault, vent_angle, pump_water_enable,
            is_event, alarm_level, alarm_reason, action
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_time,
            BATCH_ID,
            data["co2_percent"],
            data["ph_val"],
            data["water_raw"],
            data["water_v"],
            data["water_level"],
            data["tem"],
            data["motor_enable"],
            data["motor_direction"],
            data["motor_pwm"],
            data["motor_actual_rpm"],
            data["motor_fault"],
            data["vent_angle"],
            data["pump_water_enable"],
            event_info["is_event"],
            event_info["alarm_level"],
            event_info["alarm_reason"],
            event_info["action"],
        ),
    )
    prune_old_rows(cursor)
    conn.commit()
    conn.close()
    return current_time


def prune_old_rows(cursor):
    cursor.execute(
        """
        DELETE FROM sensor_logs
        WHERE id NOT IN (
            SELECT id FROM sensor_logs
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (MAX_ROWS,),
    )


def get_latest_sensor_data():
    if latest_sensor_data is not None:
        data = dict(latest_sensor_data)
        age_s = max(0, int(time.time() - last_sensor_seen_ts))
        data["age_s"] = age_s
        data["status"] = "online" if age_s <= 30 else "stale"
        return enrich_latest_data(data)

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
        }

    if row is None:
        return {
            "status": "waiting_for_sensor_data",
        }

    now = time.time()
    try:
        ts = time.mktime(time.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S"))
    except Exception:
        ts = now
    age_s = max(0, int(now - ts))

    data = {
        "status": "online" if age_s <= 30 else "stale",
        "age_s": age_s,
        "device_id": DEFAULT_DEVICE_ID,
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
    return enrich_latest_data(data)


class TelemetryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif self.path == "/latest":
            self.send_json(200, get_latest_sensor_data())
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        global latest_sensor_data, last_sensor_seen_ts, last_dispatched_action, last_dispatched_at

        if self.path == "/queue_action":
            self.handle_queue_action()
            return

        if self.path != "/telemetry":
            self.send_json(404, {"error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))
            data = normalize_payload(payload)
            event_info = evaluate_event(data)
            action_info = pop_action(data["device_id"])

            last_sensor_seen_ts = time.time()
            if action_info["action"] != ACTION_KEEP:
                last_dispatched_action = action_info["action"]
                last_dispatched_at = last_sensor_seen_ts

            base_latest_data = {
                "status": "online",
                "device_id": data["device_id"],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "co2_percent": data["co2_percent"],
                "ph_val": data["ph_val"],
                "water_raw": data["water_raw"],
                "water_v": data["water_v"],
                "water_level": data["water_level"],
                "temp_c": data["tem"],
                "motor_enable": data["motor_enable"],
                "motor_direction": data["motor_direction"],
                "motor_pwm": data["motor_pwm"],
                "motor_actual_rpm": data["motor_actual_rpm"],
                "motor_fault": data["motor_fault"],
                "vent_angle": data["vent_angle"],
                "pump_water_enable": data["pump_water_enable"],
                "alarm_level": event_info["alarm_level"],
                "alarm_reason": event_info["alarm_reason"],
                "event_action": event_info["action"],
                "queued_action": action_info["action"],
                "action": action_info["action"] if action_info["action"] != ACTION_KEEP else event_info["action"],
            }
            latest_sensor_data = enrich_latest_data(base_latest_data, event_info)
            save_reason = should_save(event_info)
            saved_at = insert_row(data, event_info) if save_reason else None

            print(
                "http rx -> "
                f"pH:{data['ph_val']:.2f} "
                f"CO2:{data['co2_percent']:.4f}% "
                f"temp:{data['tem']:.2f}C "
                f"water:{data['water_level']}/4 "
                f"motor:{data['motor_pwm']:.1f}% "
                f"{data['motor_actual_rpm']:.2f}rpm "
                f"vent:{data['vent_angle']:.0f}deg "
                f"pump:{data['pump_water_enable']} "
                f"fault:{data['motor_fault']} "
                f"alarm:{event_info['alarm_reason']:<28} "
                f"saved:{save_reason or 'no'} "
                f"action:{action_info['action']}"
            )

            self.send_json(
                200,
                {
                    "ok": True,
                    "saved": save_reason,
                    "saved_at": saved_at,
                    "alarm": event_info,
                    "action": action_info["action"],
                    "action_source": action_info["action_source"],
                    "queued_at": action_info["queued_at"],
                },
            )
        except Exception as e:
            self.send_json(400, {"ok": False, "error": str(e)})

    def handle_queue_action(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))
            action = payload.get("action", ACTION_KEEP)
            device_id = payload.get("device_id", DEFAULT_DEVICE_ID)
            ok = enqueue_action(action, device_id=device_id, source="manual_http")
            self.send_json(
                200 if ok else 400,
                {
                    "ok": ok,
                    "device_id": device_id,
                    "action": normalize_action(action),
                },
            )
        except Exception as e:
            self.send_json(400, {"ok": False, "error": str(e)})

    def log_message(self, fmt, *args):
        return

    def send_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    init_db().close()
    server = ThreadingHTTPServer((HOST, PORT), TelemetryHandler)
    print(f"HTTP telemetry receiver listening on http://{HOST}:{PORT}/telemetry")
    print(
        f"normal save interval: {NORMAL_SAVE_INTERVAL_S}s | "
        f"event repeat interval: {EVENT_REPEAT_INTERVAL_S}s | max rows: {MAX_ROWS}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHTTP receiver stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

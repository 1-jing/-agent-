import os
import sqlite3
import time


RX_PORT = "/dev/ttyS3"
BAUD_RATE = 9600
DB_FILE = "ferment_twin.db"
BATCH_ID = "EXP_20260422_01"

# Store ordinary trend data once per minute. Store abnormal events immediately.
NORMAL_SAVE_INTERVAL_S = 60
EVENT_REPEAT_INTERVAL_S = 60
MAX_ROWS = 10000

# First-stage competition/demo thresholds. Tune after real fermentation data arrives.
PH_LOW = 3.8
PH_HIGH = 8.8
TEMP_LOW_C = 5.0
TEMP_HIGH_C = 28.0
CO2_HIGH_PERCENT = 1.0
WATER_HIGH_LEVEL = 4


EXTRA_COLUMNS = {
    "co2_percent": "REAL",
    "motor_enable": "INTEGER",
    "motor_direction": "TEXT",
    "motor_pwm": "REAL",
    "motor_actual_rpm": "REAL",
    "motor_fault": "TEXT",
    "is_event": "INTEGER DEFAULT 0",
    "alarm_level": "TEXT DEFAULT 'normal'",
    "alarm_reason": "TEXT DEFAULT 'none'",
    "action": "TEXT DEFAULT 'none'",
    "is_synced": "INTEGER DEFAULT 0",
}


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
    cursor.execute("PRAGMA table_info(sensor_logs)")
    existing = {row[1] for row in cursor.fetchall()}

    for name, sql_type in EXTRA_COLUMNS.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE sensor_logs ADD COLUMN {name} {sql_type}")

    conn.commit()


def parse_frame(data_str):
    parts = data_str.split(",")
    if len(parts) != 11:
        return None

    return {
        "co2_percent": float(parts[0]),
        "ph_val": float(parts[1]),
        "water_raw": int(parts[2]),
        "water_v": float(parts[3]),
        "water_level": int(parts[4]),
        "tem": float(parts[5]),
        "motor_enable": int(parts[6]),
        "motor_direction": parts[7],
        "motor_pwm": float(parts[8]),
        "motor_actual_rpm": float(parts[9]),
        "motor_fault": parts[10],
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
        level = "warning" if level == "normal" else level

    is_event = bool(reasons)
    return {
        "is_event": 1 if is_event else 0,
        "alarm_level": level,
        "alarm_reason": "|".join(reasons) if reasons else "none",
        "action": "|".join(dict.fromkeys(actions)) if actions else "none",
    }


def insert_row(conn, cursor, data, event_info):
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO sensor_logs (
            timestamp, batch_id,
            co2_percent, ph_val, water_raw, water_v, water_level, tem,
            motor_enable, motor_direction, motor_pwm, motor_actual_rpm,
            motor_fault, is_event, alarm_level, alarm_reason, action
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            event_info["is_event"],
            event_info["alarm_level"],
            event_info["alarm_reason"],
            event_info["action"],
        ),
    )
    conn.commit()
    prune_old_rows(conn, cursor)
    return current_time


def prune_old_rows(conn, cursor):
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
    conn.commit()


def should_save_event(event_info, last_event_reason, last_event_save_time):
    if not event_info["is_event"]:
        return False, last_event_reason, last_event_save_time

    now = time.monotonic()
    reason = event_info["alarm_reason"]
    if reason != last_event_reason or now - last_event_save_time >= EVENT_REPEAT_INTERVAL_S:
        return True, reason, now

    return False, last_event_reason, last_event_save_time


def main():
    print(f"2K1000LA SQLite gateway started | batch: {BATCH_ID}")
    print(
        f"normal save interval: {NORMAL_SAVE_INTERVAL_S}s | "
        f"event repeat interval: {EVENT_REPEAT_INTERVAL_S}s | max rows: {MAX_ROWS}"
    )

    conn = init_db()
    cursor = conn.cursor()
    os.system(f"stty -F {RX_PORT} {BAUD_RATE} raw -echo")

    last_normal_save_time = 0.0
    last_event_save_time = 0.0
    last_event_reason = "none"

    try:
        with open(RX_PORT, "rb", buffering=0) as ser:
            serial_buf = b""
            while True:
                char = ser.read(1)
                serial_buf += char

                if char != b"\n":
                    continue

                try:
                    data_str = serial_buf.decode("ascii", errors="ignore").strip()
                    data = parse_frame(data_str)
                    if data is None:
                        if data_str:
                            print(f"\nignored frame with unexpected fields: {data_str}")
                        continue

                    event_info = evaluate_event(data)
                    now = time.monotonic()
                    save_reason = None

                    save_event, last_event_reason, last_event_save_time = should_save_event(
                        event_info,
                        last_event_reason,
                        last_event_save_time,
                    )
                    if save_event:
                        save_reason = "event"
                    elif now - last_normal_save_time >= NORMAL_SAVE_INTERVAL_S:
                        event_info = {
                            "is_event": 0,
                            "alarm_level": "normal",
                            "alarm_reason": "none",
                            "action": "none",
                        }
                        save_reason = "normal"
                        last_normal_save_time = now

                    print(
                        "rx -> "
                        f"pH:{data['ph_val']:.2f} "
                        f"CO2:{data['co2_percent']:.4f}% "
                        f"temp:{data['tem']:.2f}C "
                        f"water:{data['water_level']}/4 "
                        f"motor:{data['motor_pwm']:.1f}% "
                        f"{data['motor_actual_rpm']:.2f}rpm "
                        f"fault:{data['motor_fault']} "
                        f"alarm:{event_info['alarm_reason']:<28}",
                        end="\r",
                    )

                    if save_reason:
                        saved_at = insert_row(conn, cursor, data, event_info)
                        print(
                            f"\n[{saved_at}] saved {save_reason}: "
                            f"{event_info['alarm_level']} "
                            f"{event_info['alarm_reason']} "
                            f"action={event_info['action']}"
                        )

                except Exception as e:
                    print(f"\nparse error: {e}")
                finally:
                    serial_buf = b""

    except KeyboardInterrupt:
        print("\nSQLite gateway stopped")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

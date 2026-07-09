import os
import sqlite3
import time


RX_PORT = "/dev/ttyS3"
BAUD_RATE = 9600
DB_FILE = "ferment_twin.db"
BATCH_ID = "EXP_20260422_01"
BUFFER_SIZE = 10


MOTOR_COLUMNS = {
    "co2_percent": "REAL",
    "motor_enable": "INTEGER",
    "motor_direction": "TEXT",
    "motor_pwm": "REAL",
    "motor_actual_rpm": "REAL",
    "motor_fault": "TEXT",
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
            co2_ppm INTEGER,
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
            is_synced INTEGER DEFAULT 0
        )
        """
    )
    ensure_motor_columns(conn, cursor)
    conn.commit()
    return conn


def ensure_motor_columns(conn, cursor):
    cursor.execute("PRAGMA table_info(sensor_logs)")
    existing = {row[1] for row in cursor.fetchall()}

    for name, sql_type in MOTOR_COLUMNS.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE sensor_logs ADD COLUMN {name} {sql_type}")

    if "is_synced" not in existing:
        cursor.execute("ALTER TABLE sensor_logs ADD COLUMN is_synced INTEGER DEFAULT 0")

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


def insert_batch(cursor, data_buffer):
    cursor.executemany(
        """
        INSERT INTO sensor_logs (
            timestamp, batch_id,
            co2_percent, ph_val, water_raw, water_v, water_level, tem,
            motor_enable, motor_direction, motor_pwm, motor_actual_rpm,
            motor_fault
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data_buffer,
    )


def main():
    print(f"2K1000LA SQLite gateway started | batch: {BATCH_ID}")
    conn = init_db()
    cursor = conn.cursor()
    os.system(f"stty -F {RX_PORT} {BAUD_RATE} raw -echo")
    data_buffer = []

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
                    parsed = parse_frame(data_str)
                    if parsed is None:
                        if data_str:
                            print(f"\nignored frame with unexpected fields: {data_str}")
                    else:
                        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                        data_buffer.append(
                            (
                                current_time,
                                BATCH_ID,
                                parsed["co2_percent"],
                                parsed["ph_val"],
                                parsed["water_raw"],
                                parsed["water_v"],
                                parsed["water_level"],
                                parsed["tem"],
                                parsed["motor_enable"],
                                parsed["motor_direction"],
                                parsed["motor_pwm"],
                                parsed["motor_actual_rpm"],
                                parsed["motor_fault"],
                            )
                        )

                        print(
                            "rx -> "
                            f"pH:{parsed['ph_val']:.2f} "
                            f"CO2:{parsed['co2_percent']:.4f}% "
                            f"temp:{parsed['tem']:.2f}C "
                            f"water:{parsed['water_level']}/4 "
                            f"motor:{parsed['motor_pwm']:.1f}% "
                            f"{parsed['motor_actual_rpm']:.2f}rpm "
                            f"fault:{parsed['motor_fault']} "
                            f"buffer:{len(data_buffer)}/{BUFFER_SIZE}",
                            end="\r",
                        )

                        if len(data_buffer) >= BUFFER_SIZE:
                            insert_batch(cursor, data_buffer)
                            conn.commit()
                            print(f"\n[{current_time}] saved {len(data_buffer)} rows")
                            data_buffer.clear()

                except Exception as e:
                    print(f"\nparse error: {e}")
                finally:
                    serial_buf = b""

    except KeyboardInterrupt:
        if data_buffer:
            insert_batch(cursor, data_buffer)
            conn.commit()
        print("\nSQLite gateway stopped")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

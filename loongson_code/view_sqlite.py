import sqlite3


DB_FILE = "ferment_twin.db"


def browse_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM sensor_logs")
    total = cursor.fetchone()[0]
    print(f"total rows: {total}")

    cursor.execute("PRAGMA table_info(sensor_logs)")
    columns = {row[1] for row in cursor.fetchall()}
    vent_expr = "vent_angle" if "vent_angle" in columns else "0 AS vent_angle"

    cursor.execute(
        f"""
        SELECT
            id, timestamp, co2_percent, ph_val, water_level, tem,
            motor_direction, motor_pwm, motor_actual_rpm, motor_fault,
            {vent_expr}, is_event, alarm_level, alarm_reason, action
        FROM sensor_logs
        ORDER BY id DESC
        LIMIT 10
        """
    )
    rows = cursor.fetchall()

    print("\nlatest 10 rows:")
    print("ID | time | CO2 | pH | water | temp | motor")
    print("-" * 90)
    for row in rows:
        (
            row_id,
            timestamp,
            co2_percent,
            ph_val,
            water_level,
            tem,
            motor_direction,
            motor_pwm,
            motor_actual_rpm,
            motor_fault,
            vent_angle,
            is_event,
            alarm_level,
            alarm_reason,
            action,
        ) = row
        print(
            f"{row_id} | {timestamp} | {co2_percent:.4f}% | {ph_val:.2f} | "
            f"{water_level}/4 | {tem:.2f}C | {motor_direction} "
            f"{motor_pwm:.1f}% {motor_actual_rpm:.2f}rpm "
            f"vent={vent_angle:.0f}deg fault={motor_fault} | "
            f"event={is_event} {alarm_level} {alarm_reason} action={action}"
        )

    conn.close()


if __name__ == "__main__":
    browse_data()

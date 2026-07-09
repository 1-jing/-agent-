import os
import threading
import time

import co2
import ph
import tem
import water
from duoji import ServoController
from tb6612_loongson_pwm3_gpio72_75_74 import TB6612Motor
from water_pump import PUMP_GPIO, WaterPump


# 2K0300 -> 2K1000LA wireless HTTP endpoint.
# Change this IP to the 2K1000LA address shown by ifconfig/ip addr.
HTTP_ENDPOINT = "http://192.168.99.112:8080/telemetry"
SEND_INTERVAL_S = 1.0

# Fermenter stirring defaults. Change these two values for the first-stage demo.
MOTOR_AUTO_START = True
MOTOR_DEFAULT_PWM = 20.0
last_action = "keep"
MOTOR_PWM_LEVELS = {0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100}

# Exhaust valve servo. Adjust these two angles if your valve direction is reversed.
VENT_SERVO_PWMCHIP = 2
VENT_SERVO_CHANNEL = 0
VENT_CLOSE_ANGLE = 0
VENT_MID_ANGLE = 45
VENT_OPEN_ANGLE = 90
actuator_state = {
    "vent_angle": VENT_CLOSE_ANGLE,
    "pump_water_enable": 0,
}


sensor_data = {
    "co2_ppm": 0,
    "ph_val": 7.0,
    "water_raw": 0,
    "water_v": 0.0,
    "water_level": 0,
    "temp_c": 0.0,
}


def build_payload(motor):
    motor.update_fault()
    motor_enable = 1 if motor.direction in ("forward", "backward", "brake") else 0
    return {
        "device_id": "2k0300-fermenter-node",
        "co2_percent": round(sensor_data["co2_ppm"] / 10000.0, 4),
        "ph_val": sensor_data["ph_val"],
        "water_raw": sensor_data["water_raw"],
        "water_v": sensor_data["water_v"],
        "water_level": sensor_data["water_level"],
        "tem": sensor_data["temp_c"],
        "motor_enable": motor_enable,
        "motor_direction": motor.direction,
        "motor_pwm": round(motor.current_pwm, 1),
        "motor_actual_rpm": round(motor.encoder.actual_rpm, 2),
        "motor_fault": motor.fault,
        "vent_angle": actuator_state["vent_angle"],
        "pump_water_enable": actuator_state["pump_water_enable"],
    }


def post_json(url, payload):
    body = build_json(payload)
    command = (
        "wget -q -O - "
        "--header='Content-Type: application/json' "
        f"--post-data={shell_single_quote(body)} "
        f"{shell_single_quote(url)}"
    )
    status = os.system(command + " > /tmp/ferment_http_reply.txt 2>/tmp/ferment_http_error.txt")
    if status != 0:
        try:
            with open("/tmp/ferment_http_error.txt", "r") as f:
                return False, body, f.read().strip()
        except OSError:
            return False, body, f"wget exit status {status}"

    try:
        with open("/tmp/ferment_http_reply.txt", "r") as f:
            return True, body, f.read().strip()
    except OSError:
        return True, body, ""


def build_json(payload):
    parts = []
    for key, value in payload.items():
        if isinstance(value, str):
            parts.append(f'"{key}":"{json_escape(value)}"')
        else:
            parts.append(f'"{key}":{value}')
    return "{" + ",".join(parts) + "}"


def json_escape(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def shell_single_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def extract_action(reply):
    value = extract_top_level_string(reply, "action")
    return value if value else "keep"


def extract_top_level_string(text, key):
    target = '"' + key + '"'
    depth = 0
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            if depth == 1 and text.startswith(target, i):
                j = i + len(target)
                while j < len(text) and text[j] in " \t\r\n":
                    j += 1
                if j >= len(text) or text[j] != ":":
                    i += 1
                    continue
                j += 1
                while j < len(text) and text[j] in " \t\r\n":
                    j += 1
                if j >= len(text) or text[j] != '"':
                    return None
                j += 1
                out = []
                value_escape = False
                while j < len(text):
                    c = text[j]
                    if value_escape:
                        out.append(c)
                        value_escape = False
                    elif c == "\\":
                        value_escape = True
                    elif c == '"':
                        return "".join(out)
                    else:
                        out.append(c)
                    j += 1
                return None
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        i += 1
    return None


def set_vent_angle(vent_servo, angle):
    angle = max(0, min(180, int(float(angle))))
    vent_servo.set_angle(angle)
    actuator_state["vent_angle"] = angle


def set_water_pump(pump_gpio, enable):
    pump_gpio.set_enabled(enable)
    actuator_state["pump_water_enable"] = 1 if enable else 0
    print(f"\n[action] water pump GPIO{PUMP_GPIO} -> {actuator_state['pump_water_enable']}")


def apply_action(motor, vent_servo, pump_gpio, action):
    global last_action

    if action in ("", "keep", "NONE", "none"):
        return
    if action == last_action:
        return

    if action == "motor_stop" or action == "motor_pwm_0":
        motor.stop()
    elif action.startswith("motor_pwm_"):
        try:
            pwm = int(action.split("_")[-1])
        except ValueError:
            print(f"\n[action] rejected invalid motor action: {action}")
            return
        if pwm not in MOTOR_PWM_LEVELS:
            print(f"\n[action] rejected out-of-range motor PWM: {action}")
            return
        motor.forward(pwm)
    elif action == "pump_water_on":
        set_water_pump(pump_gpio, True)
    elif action == "pump_water_off":
        set_water_pump(pump_gpio, False)
    elif action == "vent_open":
        set_vent_angle(vent_servo, VENT_OPEN_ANGLE)
    elif action == "vent_close":
        set_vent_angle(vent_servo, VENT_CLOSE_ANGLE)
    elif action == "vent_mid":
        set_vent_angle(vent_servo, VENT_MID_ANGLE)
    elif action.startswith("vent_angle_"):
        try:
            angle = float(action.split("_")[-1])
        except ValueError:
            print(f"\n[action] rejected invalid vent action: {action}")
            return
        set_vent_angle(vent_servo, angle)
    else:
        print(f"\n[action] rejected unsupported action: {action}")
        return

    last_action = action
    print(f"\n[action] executed: {action}")


def main():
    print("2K0300 fermenter acquisition node starting...")
    print(f"wireless target -> {HTTP_ENDPOINT}")

    threading.Thread(
        target=co2.read_co2_raw,
        args=(sensor_data, "/dev/ttyS1"),
        daemon=True,
    ).start()

    motor = TB6612Motor()
    motor.setup()
    if MOTOR_AUTO_START:
        motor.forward(MOTOR_DEFAULT_PWM)

    vent_servo = ServoController(pwmchip=VENT_SERVO_PWMCHIP, channel=VENT_SERVO_CHANNEL)
    vent_servo.setup()
    set_vent_angle(vent_servo, VENT_CLOSE_ANGLE)

    pump_gpio = WaterPump(PUMP_GPIO)
    pump_gpio.setup(initial_off=True)
    set_water_pump(pump_gpio, False)

    try:
        while True:
            w_raw, w_v, w_lv = water.read_water()
            sensor_data["water_raw"] = w_raw
            sensor_data["water_v"] = round(w_v, 3)
            sensor_data["water_level"] = w_lv

            ph_val, _ = ph.read_ph_value()
            if ph_val is not None:
                sensor_data["ph_val"] = round(ph_val, 2)

            t_val = tem.read_temperature()
            if t_val is not None:
                sensor_data["temp_c"] = t_val

            payload = build_payload(motor)
            ok, body, reply = post_json(HTTP_ENDPOINT, payload)
            if ok:
                action = extract_action(reply)
                apply_action(motor, vent_servo, pump_gpio, action)
                print(
                    f"{'posted -> ' + body + ' reply=' + reply:<180}",
                    end="\r",
                )
            else:
                print(f"{'post failed -> ' + reply:<180}", end="\r")

            time.sleep(SEND_INTERVAL_S)

    except KeyboardInterrupt:
        print("\nnode stopped")
    finally:
        motor.cleanup()
        try:
            vent_servo.disable()
            vent_servo.unexport()
        except Exception as e:
            print(f"\nservo cleanup failed: {e}")
        try:
            pump_gpio.cleanup(turn_off=True, unexport=True)
        except Exception as e:
            print(f"\npump GPIO cleanup failed: {e}")


if __name__ == "__main__":
    main()

import os


RX_PORT = "/dev/ttyS3"
BAUD_RATE = 9600


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
        "temp_c": float(parts[5]),
        "motor_enable": int(parts[6]),
        "motor_direction": parts[7],
        "motor_pwm": float(parts[8]),
        "motor_actual_rpm": float(parts[9]),
        "motor_fault": parts[10],
    }


def main():
    print("2K1000LA receiver started, waiting for CSV frames...")
    os.system(f"stty -F {RX_PORT} {BAUD_RATE} raw -echo")

    try:
        with open(RX_PORT, "rb", buffering=0) as ser:
            buffer = b""
            while True:
                char = ser.read(1)
                buffer += char

                if char != b"\n":
                    continue

                try:
                    data_str = buffer.decode("ascii", errors="ignore").strip()
                    data = parse_frame(data_str)
                    if data is None:
                        if data_str:
                            print(f"ignored frame: {data_str}")
                    else:
                        print(
                            "received | "
                            f"CO2:{data['co2_percent']:.4f}% | "
                            f"pH:{data['ph_val']:.2f} | "
                            f"water:{data['water_level']}/4 "
                            f"(raw:{data['water_raw']}, {data['water_v']:.3f}V) | "
                            f"temp:{data['temp_c']:.2f}C | "
                            f"motor:{data['motor_direction']} "
                            f"{data['motor_pwm']:.1f}% "
                            f"{data['motor_actual_rpm']:.2f}rpm "
                            f"fault:{data['motor_fault']}"
                        )
                except Exception as e:
                    print(f"parse error: {e}")
                finally:
                    buffer = b""

    except KeyboardInterrupt:
        print("\nreceiver stopped")


if __name__ == "__main__":
    main()

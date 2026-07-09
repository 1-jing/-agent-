import argparse
import os
import time


PUMP_GPIO = 73
GPIO_BASE = "/sys/class/gpio"


class WaterPump:
    def __init__(self, gpio_num=PUMP_GPIO, active_high=True):
        self.gpio_num = gpio_num
        self.active_high = active_high
        self.path = f"{GPIO_BASE}/gpio{self.gpio_num}"

    def setup(self, initial_off=True):
        if not os.path.exists(self.path):
            with open(f"{GPIO_BASE}/export", "w", encoding="ascii") as f:
                f.write(str(self.gpio_num))
            time.sleep(0.1)

        with open(f"{self.path}/direction", "w", encoding="ascii") as f:
            f.write("out")

        if initial_off:
            self.off()

    def on(self):
        self._write_level(True)

    def off(self):
        self._write_level(False)

    def set_enabled(self, enable):
        if enable:
            self.on()
        else:
            self.off()

    def pulse(self, seconds):
        self.on()
        time.sleep(max(0.0, float(seconds)))
        self.off()

    def cleanup(self, turn_off=True, unexport=True):
        if turn_off:
            self.off()
        if unexport and os.path.exists(self.path):
            with open(f"{GPIO_BASE}/unexport", "w", encoding="ascii") as f:
                f.write(str(self.gpio_num))

    def _write_level(self, enabled):
        level = enabled if self.active_high else not enabled
        with open(f"{self.path}/value", "w", encoding="ascii") as f:
            f.write("1" if level else "0")


def parse_args():
    parser = argparse.ArgumentParser(description="Water pump MOSFET control on GPIO73")
    parser.add_argument(
        "command",
        choices=("on", "off", "pulse"),
        help="on: GPIO73 high, off: GPIO73 low, pulse: turn on for --seconds then off",
    )
    parser.add_argument("--seconds", type=float, default=3.0, help="pulse duration, default: 3")
    parser.add_argument("--keep-exported", action="store_true", help="keep gpio73 exported on exit")
    return parser.parse_args()


def main():
    args = parse_args()
    pump = WaterPump(PUMP_GPIO)
    pump.setup(initial_off=False)

    try:
        if args.command == "on":
            pump.on()
            print(f"water pump ON: GPIO{PUMP_GPIO}=1")
            return

        if args.command == "off":
            pump.off()
            print(f"water pump OFF: GPIO{PUMP_GPIO}=0")
            return

        print(f"water pump ON for {args.seconds:.1f}s: GPIO{PUMP_GPIO}=1")
        pump.pulse(args.seconds)
        print(f"water pump OFF: GPIO{PUMP_GPIO}=0")
    finally:
        if args.command == "pulse":
            pump.cleanup(turn_off=True, unexport=not args.keep_exported)


if __name__ == "__main__":
    main()

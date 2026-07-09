import argparse

from water_pump import PUMP_GPIO, WaterPump


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

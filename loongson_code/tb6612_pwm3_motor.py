import argparse
import os
import time


class PWMController:
    def __init__(self, pwmchip=3, channel=0):
        self.pwmchip = pwmchip
        self.channel = channel
        self.base_path = f"/sys/class/pwm/pwmchip{self.pwmchip}"
        self.pwm_path = f"{self.base_path}/pwm{self.channel}"

        if not os.path.exists(self.base_path):
            raise FileNotFoundError(f"PWM chip pwmchip{self.pwmchip} does not exist")

    def export(self):
        if not os.path.exists(self.pwm_path):
            with open(f"{self.base_path}/export", "w", encoding="ascii") as f:
                f.write(str(self.channel))
            time.sleep(0.1)

    def unexport(self):
        if os.path.exists(self.pwm_path):
            with open(f"{self.base_path}/unexport", "w", encoding="ascii") as f:
                f.write(str(self.channel))

    def enable(self):
        self._write_value("enable", "1")

    def disable(self):
        if os.path.exists(f"{self.pwm_path}/enable"):
            self._write_value("enable", "0")

    def set_period(self, period_ns):
        self._write_value("period", str(int(period_ns)))

    def set_duty_cycle(self, duty_ns):
        self._write_value("duty_cycle", str(int(duty_ns)))

    def _write_value(self, filename, value):
        try:
            with open(f"{self.pwm_path}/{filename}", "w", encoding="ascii") as f:
                f.write(value)
        except Exception as e:
            raise RuntimeError(f"failed to write {filename}: {e}") from e


class GPIOPin:
    def __init__(self, gpio_num, name="gpio"):
        self.gpio_num = gpio_num
        self.name = name
        self.path = f"/sys/class/gpio/gpio{self.gpio_num}"

    def export(self):
        if not os.path.exists(self.path):
            with open("/sys/class/gpio/export", "w", encoding="ascii") as f:
                f.write(str(self.gpio_num))
            time.sleep(0.1)

        with open(f"{self.path}/direction", "w", encoding="ascii") as f:
            f.write("out")

    def write(self, value):
        with open(f"{self.path}/value", "w", encoding="ascii") as f:
            f.write("1" if value else "0")

    def unexport(self):
        if os.path.exists(self.path):
            with open("/sys/class/gpio/unexport", "w", encoding="ascii") as f:
                f.write(str(self.gpio_num))


class TB6612Motor:
    def __init__(
        self,
        ain1_gpio,
        ain2_gpio,
        stby_gpio=None,
        pwmchip=3,
        pwm_channel=0,
        frequency_hz=10000,
        invert_pwm=False,
    ):
        self.pwm = PWMController(pwmchip=pwmchip, channel=pwm_channel)
        self.ain1 = GPIOPin(ain1_gpio, "AIN1")
        self.ain2 = GPIOPin(ain2_gpio, "AIN2")
        self.stby = GPIOPin(stby_gpio, "STBY") if stby_gpio is not None else None
        self.frequency_hz = frequency_hz
        self.period_ns = int(1_000_000_000 / self.frequency_hz)
        self.invert_pwm = invert_pwm

    def setup(self):
        self.ain1.export()
        self.ain2.export()

        if self.stby is not None:
            self.stby.export()
            self.stby.write(1)

        self.pwm.export()

        # TB6612 manual recommends 10 kHz PWM. Set duty to zero before enabling.
        self.pwm.disable()
        self.pwm.set_duty_cycle(0)
        self.pwm.set_period(self.period_ns)
        self.pwm.set_duty_cycle(self._speed_to_duty_ns(0))
        self.pwm.enable()

        self.stop()
        print(
            f"TB6612 ready: pwmchip{self.pwm.pwmchip}/pwm{self.pwm.channel}, "
            f"{self.frequency_hz} Hz"
        )

    def forward(self, speed_percent):
        self.ain1.write(1)
        self.ain2.write(0)
        self.set_speed(speed_percent)
        print(f"forward {self._clamp_speed(speed_percent):.1f}%")

    def backward(self, speed_percent):
        self.ain1.write(0)
        self.ain2.write(1)
        self.set_speed(speed_percent)
        print(f"backward {self._clamp_speed(speed_percent):.1f}%")

    def stop(self):
        self.set_speed(0)
        self.ain1.write(0)
        self.ain2.write(0)
        print("stop")

    def brake(self):
        self.ain1.write(1)
        self.ain2.write(1)
        self.set_speed(100)
        print("brake")

    def standby(self):
        self.stop()
        if self.stby is not None:
            self.stby.write(0)
        print("standby")

    def wakeup(self):
        if self.stby is not None:
            self.stby.write(1)
        print("wakeup")

    def set_speed(self, speed_percent):
        self.pwm.set_duty_cycle(self._speed_to_duty_ns(speed_percent))

    def cleanup(self, keep_exported=False):
        try:
            self.stop()
        finally:
            self.pwm.disable()

        if not keep_exported:
            self.pwm.unexport()
            self.ain1.unexport()
            self.ain2.unexport()
            if self.stby is not None:
                self.stby.unexport()

    def _speed_to_duty_ns(self, speed_percent):
        speed = self._clamp_speed(speed_percent)
        duty = int(self.period_ns * speed / 100.0)
        if self.invert_pwm:
            duty = self.period_ns - duty
        return duty

    @staticmethod
    def _clamp_speed(speed_percent):
        return max(0.0, min(100.0, float(speed_percent)))


def parse_args():
    parser = argparse.ArgumentParser(description="TB6612 motor test for Loongson 2K0300")
    parser.add_argument("--ain1", type=int, required=True, help="GPIO number connected to AIN1")
    parser.add_argument("--ain2", type=int, required=True, help="GPIO number connected to AIN2")
    parser.add_argument("--stby", type=int, default=None, help="GPIO number connected to STBY")
    parser.add_argument("--pwmchip", type=int, default=3, help="PWM chip number, default: 3")
    parser.add_argument("--channel", type=int, default=0, help="PWM channel number, default: 0")
    parser.add_argument("--freq", type=int, default=10000, help="PWM frequency Hz, default: 10000")
    parser.add_argument("--invert-pwm", action="store_true", help="Invert PWM duty if hardware is inverted")
    parser.add_argument("--keep-exported", action="store_true", help="Do not unexport sysfs nodes on exit")
    return parser.parse_args()


def main():
    args = parse_args()
    motor = TB6612Motor(
        ain1_gpio=args.ain1,
        ain2_gpio=args.ain2,
        stby_gpio=args.stby,
        pwmchip=args.pwmchip,
        pwm_channel=args.channel,
        frequency_hz=args.freq,
        invert_pwm=args.invert_pwm,
    )

    try:
        motor.setup()
        print("Commands: f SPEED | b SPEED | s | brake | wake | standby | q")
        print("Example: f 40")

        while True:
            cmd = input("tb6612> ").strip().lower()
            if not cmd:
                continue
            if cmd == "q":
                break
            if cmd == "s":
                motor.stop()
                continue
            if cmd == "brake":
                motor.brake()
                continue
            if cmd == "wake":
                motor.wakeup()
                continue
            if cmd == "standby":
                motor.standby()
                continue

            parts = cmd.split()
            if len(parts) != 2 or parts[0] not in ("f", "b"):
                print("invalid command")
                continue

            try:
                speed = float(parts[1])
            except ValueError:
                print("speed must be a number from 0 to 100")
                continue

            if parts[0] == "f":
                motor.forward(speed)
            else:
                motor.backward(speed)

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        print("cleanup")
        motor.cleanup(keep_exported=args.keep_exported)


if __name__ == "__main__":
    main()

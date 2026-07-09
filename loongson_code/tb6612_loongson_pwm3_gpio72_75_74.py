import os
import select
import threading
import time


PWMCHIP = 3
PWM_CHANNEL = 0
PWM_FREQ_HZ = 10000

AIN1_GPIO = 72
AIN2_GPIO = 75
STBY_GPIO = 74

ENCODER_A_GPIO = 60
ENCODER_B_GPIO = 63

# Current project code uses ENC_RES=26 and REDUCTION_RATIO=28.
# Change this value if your motor's encoder line count or reduction ratio differs.
ENCODER_COUNTS_PER_REV = 26 * 28
RPM_SAMPLE_TIME_S = 0.2
STALL_PWM_THRESHOLD = 30.0
STALL_RPM_THRESHOLD = 5.0
STALL_TIME_S = 2.0

# Your board's PWM output is inverted: f 80 was slower than f 20.
INVERT_PWM = True


class PWMController:
    def __init__(self, pwmchip=PWMCHIP, channel=PWM_CHANNEL):
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
        self._write("enable", "1")

    def disable(self):
        if os.path.exists(f"{self.pwm_path}/enable") and self.is_enabled():
            self._write("enable", "0")

    def is_enabled(self):
        try:
            with open(f"{self.pwm_path}/enable", "r", encoding="ascii") as f:
                return f.read().strip() == "1"
        except OSError:
            return False

    def set_period(self, period_ns):
        self._write("period", str(int(period_ns)))

    def set_duty_cycle(self, duty_ns):
        self._write("duty_cycle", str(int(duty_ns)))

    def _write(self, filename, value):
        try:
            with open(f"{self.pwm_path}/{filename}", "w", encoding="ascii") as f:
                f.write(value)
        except Exception as e:
            raise RuntimeError(f"failed to write PWM {filename}: {e}") from e


class GPIOPin:
    def __init__(self, gpio_num):
        self.gpio_num = gpio_num
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


class EncoderGPIOPin:
    def __init__(self, gpio_num):
        self.gpio_num = gpio_num
        self.path = f"/sys/class/gpio/gpio{self.gpio_num}"

    def export(self):
        if not os.path.exists(self.path):
            with open("/sys/class/gpio/export", "w", encoding="ascii") as f:
                f.write(str(self.gpio_num))
            time.sleep(0.1)

        with open(f"{self.path}/direction", "w", encoding="ascii") as f:
            f.write("in")

        with open(f"{self.path}/edge", "w", encoding="ascii") as f:
            f.write("both")

    def read(self):
        with open(f"{self.path}/value", "r", encoding="ascii") as f:
            return 1 if f.read().strip() == "1" else 0

    def open_value(self):
        return open(f"{self.path}/value", "r", encoding="ascii")

    def unexport(self):
        if os.path.exists(self.path):
            try:
                with open(f"{self.path}/edge", "w", encoding="ascii") as f:
                    f.write("none")
            except OSError:
                pass
            with open("/sys/class/gpio/unexport", "w", encoding="ascii") as f:
                f.write(str(self.gpio_num))


class QuadratureEncoder:
    TRANSITIONS = {
        (0, 1): 1,
        (1, 3): 1,
        (3, 2): 1,
        (2, 0): 1,
        (0, 2): -1,
        (2, 3): -1,
        (3, 1): -1,
        (1, 0): -1,
    }

    def __init__(self, gpio_a=ENCODER_A_GPIO, gpio_b=ENCODER_B_GPIO):
        self.pin_a = EncoderGPIOPin(gpio_a)
        self.pin_b = EncoderGPIOPin(gpio_b)
        self.count = 0
        self.last_count = 0
        self.actual_rpm = 0.0
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.last_state = 0

    def setup(self):
        self.pin_a.export()
        self.pin_b.export()
        self.last_state = self._read_state()
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _read_state(self):
        return (self.pin_a.read() << 1) | self.pin_b.read()

    def _run(self):
        fd_a = self.pin_a.open_value()
        fd_b = self.pin_b.open_value()
        fd_map = {
            fd_a.fileno(): fd_a,
            fd_b.fileno(): fd_b,
        }
        poller = select.poll()
        poller.register(fd_a, select.POLLPRI | select.POLLERR)
        poller.register(fd_b, select.POLLPRI | select.POLLERR)

        fd_a.seek(0)
        fd_a.read()
        fd_b.seek(0)
        fd_b.read()
        last_sample = time.monotonic()

        try:
            while self.running:
                events = poller.poll(50)
                if events:
                    state = self._read_state()
                    delta = self.TRANSITIONS.get((self.last_state, state), 0)
                    if delta:
                        with self.lock:
                            self.count += delta
                    self.last_state = state

                    for fd, _ in events:
                        value_file = fd_map.get(fd)
                        if value_file is not None:
                            value_file.seek(0)
                            value_file.read()

                now = time.monotonic()
                if now - last_sample >= RPM_SAMPLE_TIME_S:
                    with self.lock:
                        current_count = self.count
                        delta_count = current_count - self.last_count
                        self.last_count = current_count

                    self.actual_rpm = (
                        abs(delta_count)
                        * 60.0
                        / ENCODER_COUNTS_PER_REV
                        / (now - last_sample)
                    )
                    last_sample = now
        finally:
            fd_a.close()
            fd_b.close()

    def get_count(self):
        with self.lock:
            return self.count

    def cleanup(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        self.pin_a.unexport()
        self.pin_b.unexport()


class TB6612Motor:
    def __init__(self):
        self.pwm = PWMController()
        self.ain1 = GPIOPin(AIN1_GPIO)
        self.ain2 = GPIOPin(AIN2_GPIO)
        self.stby = GPIOPin(STBY_GPIO)
        self.encoder = QuadratureEncoder()
        self.period_ns = int(1_000_000_000 / PWM_FREQ_HZ)
        self.ready = False
        self.current_pwm = 0.0
        self.direction = "stop"
        self.fault = "none"
        self.low_speed_start = None

    def setup(self):
        self.ain1.export()
        self.ain2.export()
        self.stby.export()
        self.encoder.setup()

        self.stby.write(1)
        self.pwm.export()

        # Loongson PWM sysfs may reject enable=0 when the channel is already disabled.
        # Configure in the safest order: disabled state -> period -> duty -> enable.
        if self.pwm.is_enabled():
            self.pwm.disable()
        self.pwm.set_period(self.period_ns)
        self.pwm.set_duty_cycle(0)
        self.pwm.enable()

        self.ready = True
        self.stop()
        print("TB6612 init ok")
        print(f"PWMA: pwmchip{PWMCHIP}/pwm{PWM_CHANNEL}, GPIO89, {PWM_FREQ_HZ} Hz")
        print(f"AIN1: GPIO{AIN1_GPIO}, AIN2: GPIO{AIN2_GPIO}, STBY: GPIO{STBY_GPIO}")
        print(f"Encoder: E1A=GPIO{ENCODER_A_GPIO}, E1B=GPIO{ENCODER_B_GPIO}")
        print(f"Encoder CPR: {ENCODER_COUNTS_PER_REV}")

    def forward(self, speed):
        self.ain1.write(1)
        self.ain2.write(0)
        self.direction = "forward"
        self.set_speed(speed)
        self.print_status()

    def backward(self, speed):
        self.ain1.write(0)
        self.ain2.write(1)
        self.direction = "backward"
        self.set_speed(speed)
        self.print_status()

    def stop(self):
        self.set_speed(0)
        self.ain1.write(0)
        self.ain2.write(0)
        self.direction = "stop"
        self.fault = "none"
        self.low_speed_start = None
        print("stop")

    def brake(self):
        self.ain1.write(1)
        self.ain2.write(1)
        self.direction = "brake"
        self.set_speed(100)
        self.print_status()

    def standby(self):
        self.stop()
        self.stby.write(0)
        print("standby")

    def wakeup(self):
        self.stby.write(1)
        print("wakeup")

    def set_speed(self, speed):
        self.current_pwm = self._clamp(speed)
        normal_duty_ns = int(self.period_ns * self.current_pwm / 100.0)
        if INVERT_PWM:
            duty_ns = self.period_ns - normal_duty_ns
        else:
            duty_ns = normal_duty_ns
        self.pwm.set_duty_cycle(duty_ns)

    def update_fault(self):
        if self.direction in ("forward", "backward") and self.current_pwm >= STALL_PWM_THRESHOLD:
            if self.encoder.actual_rpm <= STALL_RPM_THRESHOLD:
                if self.low_speed_start is None:
                    self.low_speed_start = time.monotonic()
                elif time.monotonic() - self.low_speed_start >= STALL_TIME_S:
                    self.fault = "stall_or_low_speed"
            else:
                self.low_speed_start = None
                self.fault = "none"
        else:
            self.low_speed_start = None
            self.fault = "none"

    def print_status(self):
        self.update_fault()
        print(
            "motor: "
            f"direction={self.direction}, "
            f"pwm={self.current_pwm:.1f}%, "
            f"actual_rpm={self.encoder.actual_rpm:.1f}, "
            f"encoder_count={self.encoder.get_count()}, "
            f"fault={self.fault}"
        )

    def cleanup(self):
        if self.ready:
            try:
                self.stop()
            except Exception as e:
                print(f"stop failed during cleanup: {e}")

            try:
                self.pwm.disable()
            except Exception as e:
                print(f"PWM disable failed during cleanup: {e}")

        try:
            self.pwm.unexport()
        except Exception as e:
            print(f"PWM unexport failed during cleanup: {e}")

        for pin in (self.ain1, self.ain2, self.stby):
            try:
                pin.unexport()
            except Exception as e:
                print(f"GPIO{pin.gpio_num} unexport failed during cleanup: {e}")

        try:
            self.encoder.cleanup()
        except Exception as e:
            print(f"encoder cleanup failed: {e}")

    @staticmethod
    def _clamp(speed):
        return max(0.0, min(100.0, float(speed)))


def main():
    motor = TB6612Motor()

    try:
        motor.setup()
        print("Commands: f SPEED | b SPEED | status | s | brake | wake | standby | q")
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
            if cmd == "status":
                motor.print_status()
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
                print("speed must be 0 to 100")
                continue

            if parts[0] == "f":
                motor.forward(speed)
            else:
                motor.backward(speed)

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        print("cleanup")
        motor.cleanup()


if __name__ == "__main__":
    main()

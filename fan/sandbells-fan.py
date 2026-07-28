#!/usr/bin/python3
# =============================================================================
# sandbells-fan.py — Sandbells PWM fan control
#
# Based on the Zynthian project PWM fan control script
# (https://github.com/zynthian — original zynthian-pwm-fan.py).
# Adapted and maintained for the Sandbells kiosk.
#
# Hysteresis: speed only increases after a clear temp rise, and only decreases
# after a clearer fall, to avoid accelerate/cut hunting.
# =============================================================================

import os
import signal
import time

import RPi.GPIO as GPIO

# --- hardware ---
FAN_PIN = 13          # BOARD numbering
FAN_FREQ = 100

# --- duty limits ---
FAN_STARTUP = 30.0
FAN_MIN = 25.0
SPEED_LOW = 25.0
SPEED_HIGH = 100.0

# --- temperature curve (linear map temp -> target duty) ---
TEMP_LOW = 40.0       # at/below → near SPEED_LOW
TEMP_HIGH = 75.0      # at/above → near SPEED_HIGH

# --- control ---
POLL_SEC = 2
SMOOTH_BETA = 0.05    # approach rate toward target when hysteresis allows
HEAT_UP = 2.0         # °C rise vs last decision before allowing speed-up
COOL_DN = 3.0         # °C fall vs last decision before allowing speed-down

DEBUG = False

scale_m = (SPEED_LOW - SPEED_HIGH) / (TEMP_LOW - TEMP_HIGH)
scale_b = SPEED_HIGH - (scale_m * TEMP_HIGH)


class SignalMonitor:
    def __init__(self):
        self.now = False
        signal.signal(signal.SIGINT, self.time_to_quit)
        signal.signal(signal.SIGTERM, self.time_to_quit)

    def time_to_quit(self, signum, frame):
        self.now = True

monitor = SignalMonitor()

def measure_temp():
    try:
        line = os.popen("vcgencmd measure_temp").readline()
        return float(line.replace("temp=", "").replace("'C", "").strip())
    except Exception:
        return 40.0


def clamp(lo, hi, x):
    return lo if x < lo else hi if x > hi else x


def write_pct(speed):
    try:
        with open("/run/sandbells-fan.pct", "w") as f:
            f.write(str(int(round(speed))))
    except Exception:
        pass


GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
GPIO.setup(FAN_PIN, GPIO.OUT)
pwm_fan = GPIO.PWM(FAN_PIN, FAN_FREQ)

try:
    print("[Sandbells Fan] Starting...")
    
    t0 = measure_temp()
    target0 = clamp(FAN_MIN, SPEED_HIGH, (scale_m * t0) + scale_b)
    smooth_speed = target0 if t0 >= TEMP_HIGH else max(FAN_STARTUP, target0 * 0.5)
    decision_temp = t0 - HEAT_UP - 0.1   # first iteration may increase if still needed
    pwm_fan.start(smooth_speed)
    write_pct(smooth_speed)
    
    while not monitor.now:
        temp = measure_temp()
        target_speed = clamp(FAN_MIN, SPEED_HIGH, (scale_m * temp) + scale_b)
        deficit = target_speed - smooth_speed

        # Emergency / catch-up: ignore dead-band if clearly under-cooled
        if deficit > 15 and temp >= (TEMP_LOW + TEMP_HIGH) / 2:
            beta = 0.25
            smooth_speed = smooth_speed - beta * (smooth_speed - target_speed)
            decision_temp = temp
        elif temp >= decision_temp + HEAT_UP:
            beta = 0.20 if (temp >= TEMP_HIGH or deficit > 20) else SMOOTH_BETA
            smooth_speed = smooth_speed - beta * (smooth_speed - target_speed)
            decision_temp = temp
        elif temp <= decision_temp - COOL_DN:
            beta = SMOOTH_BETA * 0.7
            smooth_speed = smooth_speed - beta * (smooth_speed - target_speed)
            decision_temp = temp
        # else hold       

        smooth_speed = clamp(FAN_MIN, SPEED_HIGH, smooth_speed)
        pwm_fan.ChangeDutyCycle(smooth_speed)
        write_pct(smooth_speed)

        if DEBUG or temp >= 70:
            print(
                f"[Fan] Temp: {temp:.1f}°C | target: {target_speed:.1f}% | "
                f"duty: {smooth_speed:.1f}% | decide@{decision_temp:.1f}°C"
            )

        time.sleep(POLL_SEC)

except Exception as e:
    print(f"[Fan] Error: {e}")
finally:
    try:
        pwm_fan.stop()
    except Exception:
        pass
    GPIO.cleanup()
    print("[Sandbells Fan] Shutdown complete.")

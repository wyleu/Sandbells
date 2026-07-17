#!/usr/bin/python3
# Sandbells PWM Fan Control
import RPi.GPIO as GPIO
import time
import os
import signal

FAN_PIN = 13
FAN_FREQ = 100
FAN_STARTUP = 35.0
FAN_MIN = 25.0
POLL_SEC = 2

TEMP_LOW = 35.0
TEMP_HIGH = 65.0
SPEED_LOW = 25.0
SPEED_HIGH = 100.0

SMOOTH_BETA = 0.08
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

def measure_temp():
    try:
        temp = os.popen("vcgencmd measure_temp").readline()
        return int(float(temp.replace("temp=", "").replace("'C", "")))
    except:
        return 40

def not_below(bound, x):
    return bound if x < bound else x

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
GPIO.setup(FAN_PIN, GPIO.OUT)
pwm_fan = GPIO.PWM(FAN_PIN, FAN_FREQ)

try:
    print("[Sandbells Fan] Starting...")
    smooth_speed = FAN_STARTUP
    monitor = SignalMonitor()
    pwm_fan.start(smooth_speed)

    while not monitor.now:
        temp = measure_temp()
        target_speed = (scale_m * temp) + scale_b
        smooth_speed = not_below(FAN_MIN, smooth_speed - (SMOOTH_BETA * (smooth_speed - target_speed)))
        pwm_fan.ChangeDutyCycle(smooth_speed)

        if DEBUG or temp >= 58:
            print(f"[Fan] Temp: {temp}°C | Speed: {smooth_speed:.1f}%")
        time.sleep(POLL_SEC)
except Exception as e:
    print(f"[Fan] Error: {e}")
finally:
    pwm_fan.stop()
    GPIO.cleanup()
    print("[Sandbells Fan] Shutdown complete.")

#!/usr/bin/env python3
"""
Speed Radar - Orange Pi Zero
Two IR sensors on GPIO pins → calculate speed → RTSP snapshot → send via Telegram

Hardware:
  - IR Sensor 1  → GPIO PA6  (physical pin 7)
  - IR Sensor 2  → GPIO PA1  (physical pin 11 / alias PA1 on OPi Zero)
  - Power supply → 3.3V (pin 1) or 5V (pin 2)
  - GND          → pin 6 or 9

Sensor logic:
  - Sensor output: LOW (0) when an object passes in front (beam interrupted)
  - Script detects falling edge (HIGH→LOW) on each sensor
"""

import time
import os
import cv2
import requests
from datetime import datetime
import threading

# ────────────────────────────────────────────────
#  CONFIGURATION — edit here
# ────────────────────────────────────────────────

RTSP_URL  = "rtsp://user:password@192.168.1.x:554/stream"
BOT_TOKEN = ""          # Telegram bot token
CHAT_ID   = ""          # Telegram chat / group ID

# Distance between the two IR sensors (in meters)
SENSOR_DISTANCE_M = 2.0   # ← adjust to your actual installation (max 2m)

# Speed limit in km/h
SPEED_LIMIT_KMH = 30.0

# GPIOs (physical BOARD numbering — Orange Pi Zero uses WiringOP)
# PA6 = WiringOP pin 6  |  PA1 = WiringOP pin 0
# Use the physical pin numbers below with OPi.GPIO in BOARD mode
GPIO_SENSOR_1 = 7    # PA6  → physical pin 7  on the 26-pin header
GPIO_SENSOR_2 = 11   # PA1  → physical pin 11 on the 26-pin header

# Timeout: if sensor 2 does not trigger within X seconds, discard the reading
TIMEOUT_SECONDS = 5.0

# ────────────────────────────────────────────────
#  GPIO IMPORT (OPi.GPIO for Orange Pi)
# ────────────────────────────────────────────────
try:
    import OPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("[WARNING] OPi.GPIO not found. Install with: pip install OPi.GPIO")
    print("[WARNING] Running in SIMULATION mode for testing.")
    GPIO_AVAILABLE = False

# ────────────────────────────────────────────────
#  GPIO SETUP
# ────────────────────────────────────────────────
def setup_gpio():
    if not GPIO_AVAILABLE:
        return
    GPIO.setmode(GPIO.BOARD)       # Physical header numbering
    GPIO.setup(GPIO_SENSOR_1, GPIO.IN, pull_up_down=GPIO.PUD_UP)   # Sensor 1 - PA6
    GPIO.setup(GPIO_SENSOR_2, GPIO.IN, pull_up_down=GPIO.PUD_UP)   # Sensor 2 - PA1
    print(f"[GPIO] Pins configured: physical {GPIO_SENSOR_1} (PA6) and {GPIO_SENSOR_2} (PA1)")

def read_sensor(physical_pin: int) -> bool:
    """Returns True if the sensor beam is blocked (LOW signal)."""
    if not GPIO_AVAILABLE:
        return False
    return GPIO.input(physical_pin) == GPIO.LOW

# ────────────────────────────────────────────────
#  RTSP SNAPSHOT
# ────────────────────────────────────────────────
def capture_photo() -> str | None:
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("[CAMERA] Failed to open RTSP stream")
        return None

    time.sleep(1)
    # Discard initial frames to avoid blank/blurry images
    for _ in range(10):
        cap.read()
        time.sleep(0.03)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("[CAMERA] Failed to capture frame")
        return None

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"/tmp/radar_{ts}.jpg"
    cv2.imwrite(filename, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"[CAMERA] Photo saved: {filename}")
    return filename

# ────────────────────────────────────────────────
#  TELEGRAM SEND
# ────────────────────────────────────────────────
def send_telegram(image_path: str, speed_kmh: float) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("[TELEGRAM] BOT_TOKEN or CHAT_ID not configured!")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    ts  = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    caption = (
        f"🚨 *SPEED ABOVE LIMIT!*\n"
        f"📍 Speed: *{speed_kmh:.1f} km/h*\n"
        f"⚠️ Limit: {SPEED_LIMIT_KMH:.0f} km/h\n"
        f"🕐 {ts}"
    )

    if not os.path.exists(image_path):
        print(f"[TELEGRAM] File not found: {image_path}")
        return False

    with open(image_path, "rb") as photo:
        resp = requests.post(
            url,
            data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": photo},
            timeout=15
        )

    if resp.status_code == 200:
        print(f"[TELEGRAM] Photo sent! Speed: {speed_kmh:.1f} km/h")
        os.remove(image_path)
        return True
    else:
        print(f"[TELEGRAM] Error {resp.status_code}: {resp.text}")
        return False

# ────────────────────────────────────────────────
#  SPEED CALCULATION
# ────────────────────────────────────────────────
def calculate_speed(time_s1: float, time_s2: float) -> float:
    """Calculates speed in km/h based on the elapsed time between the two sensors."""
    delta = abs(time_s2 - time_s1)
    if delta == 0:
        return 0.0
    speed_ms  = SENSOR_DISTANCE_M / delta
    speed_kmh = speed_ms * 3.6
    return speed_kmh

# ────────────────────────────────────────────────
#  MAIN LOOP
# ────────────────────────────────────────────────
def radar_loop():
    print(f"[RADAR] Monitoring... Limit: {SPEED_LIMIT_KMH} km/h | Distance: {SENSOR_DISTANCE_M}m")
    print(f"[RADAR] Sensor 1 → physical pin {GPIO_SENSOR_1} (PA6)")
    print(f"[RADAR] Sensor 2 → physical pin {GPIO_SENSOR_2} (PA1)")

    waiting_for_s2 = False
    time_s1        = None
    last_trigger   = 0  # anti-bounce: ignore triggers within 1s of each other

    while True:
        now = time.time()

        # ── Wait for Sensor 1
        if not waiting_for_s2:
            s1_blocked = read_sensor(GPIO_SENSOR_1)

            if s1_blocked and (now - last_trigger) > 1.0:
                time_s1        = now
                waiting_for_s2 = True
                last_trigger   = now
                print("[SENSOR 1] Triggered — waiting for sensor 2...")

        # ── Wait for Sensor 2 (after Sensor 1 fires)
        elif waiting_for_s2:
            s2_blocked = read_sensor(GPIO_SENSOR_2)

            if s2_blocked:
                time_s2        = time.time()
                waiting_for_s2 = False
                speed          = calculate_speed(time_s1, time_s2)
                print(f"[SENSOR 2] Triggered — Speed: {speed:.1f} km/h")

                if speed > SPEED_LIMIT_KMH:
                    print(f"[ALERT] {speed:.1f} km/h > {SPEED_LIMIT_KMH} km/h — capturing photo!")
                    # Capture and send in a separate thread (does not block radar)
                    def record(spd=speed):
                        photo = capture_photo()
                        if photo:
                            send_telegram(photo, spd)
                    threading.Thread(target=record, daemon=True).start()

            # Timeout: object did not reach sensor 2
            elif (now - time_s1) > TIMEOUT_SECONDS:
                print("[TIMEOUT] Sensor 2 did not trigger — resetting.")
                waiting_for_s2 = False

        time.sleep(0.005)  # 5ms polling — sufficient precision for low speeds


# ────────────────────────────────────────────────
#  ENTRY POINT
# ────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        setup_gpio()
        radar_loop()
    except KeyboardInterrupt:
        print("\n[RADAR] Stopped by user.")
    finally:
        if GPIO_AVAILABLE:
            GPIO.cleanup()
            print("[GPIO] Cleanup complete.")#!/usr/bin/env python3
"""
Speed Radar - Orange Pi Zero
Two IR sensors on GPIO pins → calculate speed → RTSP snapshot → send via Telegram

Hardware:
  - IR Sensor 1  → GPIO PA6  (physical pin 7)
  - IR Sensor 2  → GPIO PA1  (physical pin 11 / alias PA1 on OPi Zero)
  - Power supply → 3.3V (pin 1) or 5V (pin 2)
  - GND          → pin 6 or 9

Sensor logic:
  - Sensor output: LOW (0) when an object passes in front (beam interrupted)
  - Script detects falling edge (HIGH→LOW) on each sensor
"""

import time
import os
import cv2
import requests
from datetime import datetime
import threading

# ────────────────────────────────────────────────
#  CONFIGURATION — edit here
# ────────────────────────────────────────────────

RTSP_URL  = "rtsp://user:password@192.168.1.x:554/stream"
BOT_TOKEN = ""          # Telegram bot token
CHAT_ID   = ""          # Telegram chat / group ID

# Distance between the two IR sensors (in meters)
SENSOR_DISTANCE_M = 2.0   # ← adjust to your actual installation (max 2m)

# Speed limit in km/h
SPEED_LIMIT_KMH = 30.0

# GPIOs (physical BOARD numbering — Orange Pi Zero uses WiringOP)
# PA6 = WiringOP pin 6  |  PA1 = WiringOP pin 0
# Use the physical pin numbers below with OPi.GPIO in BOARD mode
GPIO_SENSOR_1 = 7    # PA6  → physical pin 7  on the 26-pin header
GPIO_SENSOR_2 = 11   # PA1  → physical pin 11 on the 26-pin header

# Timeout: if sensor 2 does not trigger within X seconds, discard the reading
TIMEOUT_SECONDS = 5.0

# ────────────────────────────────────────────────
#  GPIO IMPORT (OPi.GPIO for Orange Pi)
# ────────────────────────────────────────────────
try:
    import OPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("[WARNING] OPi.GPIO not found. Install with: pip install OPi.GPIO")
    print("[WARNING] Running in SIMULATION mode for testing.")
    GPIO_AVAILABLE = False

# ────────────────────────────────────────────────
#  GPIO SETUP
# ────────────────────────────────────────────────
def setup_gpio():
    if not GPIO_AVAILABLE:
        return
    GPIO.setmode(GPIO.BOARD)       # Physical header numbering
    GPIO.setup(GPIO_SENSOR_1, GPIO.IN, pull_up_down=GPIO.PUD_UP)   # Sensor 1 - PA6
    GPIO.setup(GPIO_SENSOR_2, GPIO.IN, pull_up_down=GPIO.PUD_UP)   # Sensor 2 - PA1
    print(f"[GPIO] Pins configured: physical {GPIO_SENSOR_1} (PA6) and {GPIO_SENSOR_2} (PA1)")

def read_sensor(physical_pin: int) -> bool:
    """Returns True if the sensor beam is blocked (LOW signal)."""
    if not GPIO_AVAILABLE:
        return False
    return GPIO.input(physical_pin) == GPIO.LOW

# ────────────────────────────────────────────────
#  RTSP SNAPSHOT
# ────────────────────────────────────────────────
def capture_photo() -> str | None:
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("[CAMERA] Failed to open RTSP stream")
        return None

    time.sleep(1)
    # Discard initial frames to avoid blank/blurry images
    for _ in range(10):
        cap.read()
        time.sleep(0.03)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("[CAMERA] Failed to capture frame")
        return None

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"/tmp/radar_{ts}.jpg"
    cv2.imwrite(filename, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"[CAMERA] Photo saved: {filename}")
    return filename

# ────────────────────────────────────────────────
#  TELEGRAM SEND
# ────────────────────────────────────────────────
def send_telegram(image_path: str, speed_kmh: float) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("[TELEGRAM] BOT_TOKEN or CHAT_ID not configured!")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    ts  = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    caption = (
        f"🚨 *SPEED ABOVE LIMIT!*\n"
        f"📍 Speed: *{speed_kmh:.1f} km/h*\n"
        f"⚠️ Limit: {SPEED_LIMIT_KMH:.0f} km/h\n"
        f"🕐 {ts}"
    )

    if not os.path.exists(image_path):
        print(f"[TELEGRAM] File not found: {image_path}")
        return False

    with open(image_path, "rb") as photo:
        resp = requests.post(
            url,
            data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": photo},
            timeout=15
        )

    if resp.status_code == 200:
        print(f"[TELEGRAM] Photo sent! Speed: {speed_kmh:.1f} km/h")
        os.remove(image_path)
        return True
    else:
        print(f"[TELEGRAM] Error {resp.status_code}: {resp.text}")
        return False

# ────────────────────────────────────────────────
#  SPEED CALCULATION
# ────────────────────────────────────────────────
def calculate_speed(time_s1: float, time_s2: float) -> float:
    """Calculates speed in km/h based on the elapsed time between the two sensors."""
    delta = abs(time_s2 - time_s1)
    if delta == 0:
        return 0.0
    speed_ms  = SENSOR_DISTANCE_M / delta
    speed_kmh = speed_ms * 3.6
    return speed_kmh

# ────────────────────────────────────────────────
#  MAIN LOOP
# ────────────────────────────────────────────────
def radar_loop():
    print(f"[RADAR] Monitoring... Limit: {SPEED_LIMIT_KMH} km/h | Distance: {SENSOR_DISTANCE_M}m")
    print(f"[RADAR] Sensor 1 → physical pin {GPIO_SENSOR_1} (PA6)")
    print(f"[RADAR] Sensor 2 → physical pin {GPIO_SENSOR_2} (PA1)")

    waiting_for_s2 = False
    time_s1        = None
    last_trigger   = 0  # anti-bounce: ignore triggers within 1s of each other

    while True:
        now = time.time()

        # ── Wait for Sensor 1
        if not waiting_for_s2:
            s1_blocked = read_sensor(GPIO_SENSOR_1)

            if s1_blocked and (now - last_trigger) > 1.0:
                time_s1        = now
                waiting_for_s2 = True
                last_trigger   = now
                print("[SENSOR 1] Triggered — waiting for sensor 2...")

        # ── Wait for Sensor 2 (after Sensor 1 fires)
        elif waiting_for_s2:
            s2_blocked = read_sensor(GPIO_SENSOR_2)

            if s2_blocked:
                time_s2        = time.time()
                waiting_for_s2 = False
                speed          = calculate_speed(time_s1, time_s2)
                print(f"[SENSOR 2] Triggered — Speed: {speed:.1f} km/h")

                if speed > SPEED_LIMIT_KMH:
                    print(f"[ALERT] {speed:.1f} km/h > {SPEED_LIMIT_KMH} km/h — capturing photo!")
                    # Capture and send in a separate thread (does not block radar)
                    def record(spd=speed):
                        photo = capture_photo()
                        if photo:
                            send_telegram(photo, spd)
                    threading.Thread(target=record, daemon=True).start()

            # Timeout: object did not reach sensor 2
            elif (now - time_s1) > TIMEOUT_SECONDS:
                print("[TIMEOUT] Sensor 2 did not trigger — resetting.")
                waiting_for_s2 = False

        time.sleep(0.005)  # 5ms polling — sufficient precision for low speeds


# ────────────────────────────────────────────────
#  ENTRY POINT
# ────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        setup_gpio()
        radar_loop()
    except KeyboardInterrupt:
        print("\n[RADAR] Stopped by user.")
    finally:
        if GPIO_AVAILABLE:
            GPIO.cleanup()
            print("[GPIO] Cleanup complete.")

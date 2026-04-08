import time
from adafruit_servokit import ServoKit

kit = ServoKit(channels=16)

# Channel 0 first
servo = kit.servo[0]
servo.actuation_range = 180
servo.set_pulse_width_range(500, 2500)

test_angles = [90, 80, 100, 90]

for angle in test_angles:
    print(f"Moving servo on ch0 to {angle}")
    servo.angle = angle
    time.sleep(1)

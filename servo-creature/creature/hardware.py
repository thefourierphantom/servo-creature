import board
import adafruit_mpu6050
from adafruit_servokit import ServoKit

def make_i2c():
    return board.I2C()

def make_mpu(i2c):
    return adafruit_mpu6050.MPU6050(i2c)

def make_kit(channels=16):
    return ServoKit(channels=channels)

import time
import board
import adafruit_mpu6050

i2c = board.I2C()
mpu = adafruit_mpu6050.MPU6050(i2c)

while True:
    ax, ay, az = mpu.acceleration
    gx, gy, gz = mpu.gyro
    print(
        f"accel=({ax:6.2f}, {ay:6.2f}, {az:6.2f})  "
        f"gyro=({gx:6.2f}, {gy:6.2f}, {gz:6.2f})"
    )
    time.sleep(0.1)

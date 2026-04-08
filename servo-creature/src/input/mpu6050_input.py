"""
input/mpu6050_input.py — streamlined, responsive MPU-only input path.
"""

import math
import time
from src.util.logger import get_logger

logger = get_logger("mpu6050")

_PWR_MGMT_1 = 0x6B
_ACCEL_XOUT_H = 0x3B
_WHO_AM_I = 0x75
_ACCEL_SCALE = 16384.0


class AxisMapper:
    def __init__(self, cfg: dict) -> None:
        self.reload(cfg)

    def reload(self, cfg: dict) -> None:
        self.swap = bool(cfg.get("swap_axes", True))
        self.inv_x = bool(cfg.get("invert_x", True))
        self.inv_y = bool(cfg.get("invert_y", True))
        self.sens = float(cfg.get("sensitivity", 1.1))
        self.dz = float(cfg.get("deadzone_deg", 3.0))
        logger.info(
            "AxisMapper swap=%s inv_x=%s inv_y=%s sens=%.2f dz=%.1f",
            self.swap, self.inv_x, self.inv_y, self.sens, self.dz
        )

    def apply(self, raw_roll: float, raw_pitch: float) -> tuple[float, float]:
        x, y = (raw_pitch, raw_roll) if self.swap else (raw_roll, raw_pitch)
        if self.inv_x:
            x = -x
        if self.inv_y:
            y = -y
        x *= self.sens
        y *= self.sens
        if abs(x) < self.dz:
            x = 0.0
        if abs(y) < self.dz:
            y = 0.0
        return x, y


class MockMPU6050:
    def __init__(self, cfg: dict) -> None:
        self._mapper = AxisMapper(cfg)
        self._t = 0.0
        self._manual = None

    def init(self) -> bool:
        return True

    def set_manual(self, roll: float, pitch: float) -> None:
        self._manual = (roll, pitch)

    def clear_manual(self) -> None:
        self._manual = None

    def read_raw(self) -> dict:
        return {
            "accel_x": 0.04,
            "accel_y": -0.01,
            "accel_z": 1.0,
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
        }

    def read(self) -> dict:
        self._t += 0.05
        if self._manual:
            raw_roll, raw_pitch = self._manual
        else:
            raw_roll = math.sin(self._t * 0.9) * 26.0
            raw_pitch = math.cos(self._t * 0.7) * 22.0
        roll, pitch = self._mapper.apply(raw_roll, raw_pitch)
        return {
            "roll": roll,
            "pitch": pitch,
            "raw_roll": raw_roll,
            "raw_pitch": raw_pitch,
            "accel_mag": 1.0,
        }

    def apply_calibration(self, _cal: dict) -> None:
        pass

    def reload_mapping(self, cfg: dict) -> None:
        self._mapper.reload(cfg)

    def is_available(self) -> bool:
        return True


class RealMPU6050:
    def __init__(self, cfg: dict) -> None:
        self._bus_id = int(cfg.get("i2c_bus", 1))
        addr_raw = cfg.get("address", "0x68")
        self._addr = int(str(addr_raw), 16) if isinstance(addr_raw, str) else int(addr_raw)
        self._alpha = float(cfg.get("smoothing_alpha", 0.35))
        self._mapper = AxisMapper(cfg)
        self._bus = None
        self._available = False

        self._cal = dict(ax=0.0, ay=0.0, az=0.0)
        self._sm_roll = 0.0
        self._sm_pitch = 0.0

    def init(self) -> bool:
        try:
            import smbus2
            self._bus = smbus2.SMBus(self._bus_id)
            who = self._bus.read_byte_data(self._addr, _WHO_AM_I)
            self._bus.write_byte_data(self._addr, _PWR_MGMT_1, 0x00)
            time.sleep(0.08)
            self._available = True
            logger.info("MPU6050 online bus=%d addr=0x%02X who=0x%02X", self._bus_id, self._addr, who)
            return True
        except Exception as exc:
            logger.error("MPU6050 init failed: %s", exc)
            return False

    def _read_word2c(self, reg: int) -> float:
        hi = self._bus.read_byte_data(self._addr, reg)
        lo = self._bus.read_byte_data(self._addr, reg + 1)
        val = (hi << 8) | lo
        return float(val - 65536) if val >= 0x8000 else float(val)

    def read_raw(self) -> dict:
        if not self._available:
            return {
                "accel_x": 0.0,
                "accel_y": 0.0,
                "accel_z": 1.0,
                "gyro_x": 0.0,
                "gyro_y": 0.0,
                "gyro_z": 0.0,
            }
        try:
            ax = self._read_word2c(_ACCEL_XOUT_H) / _ACCEL_SCALE
            ay = self._read_word2c(_ACCEL_XOUT_H + 2) / _ACCEL_SCALE
            az = self._read_word2c(_ACCEL_XOUT_H + 4) / _ACCEL_SCALE
            return {
                "accel_x": ax,
                "accel_y": ay,
                "accel_z": az,
                "gyro_x": 0.0,
                "gyro_y": 0.0,
                "gyro_z": 0.0,
            }
        except Exception as exc:
            logger.error("MPU6050 read_raw error: %s", exc)
            return {
                "accel_x": 0.0,
                "accel_y": 0.0,
                "accel_z": 1.0,
                "gyro_x": 0.0,
                "gyro_y": 0.0,
                "gyro_z": 0.0,
            }

    def read(self) -> dict:
        raw = self.read_raw()
        ax = raw["accel_x"] - self._cal["ax"]
        ay = raw["accel_y"] - self._cal["ay"]
        az = raw["accel_z"] - self._cal["az"]

        raw_roll = math.degrees(math.atan2(ax, az))
        raw_pitch = math.degrees(math.atan2(ay, math.sqrt(ax * ax + az * az)))

        self._sm_roll += self._alpha * (raw_roll - self._sm_roll)
        self._sm_pitch += self._alpha * (raw_pitch - self._sm_pitch)

        g_roll, g_pitch = self._mapper.apply(self._sm_roll, self._sm_pitch)
        accel_mag = math.sqrt(ax * ax + ay * ay + az * az)

        return {
            "roll": g_roll,
            "pitch": g_pitch,
            "raw_roll": self._sm_roll,
            "raw_pitch": self._sm_pitch,
            "accel_mag": accel_mag,
        }

    def apply_calibration(self, cal_data: dict) -> None:
        ao = cal_data.get("accel_offset", {})
        self._cal = {
            "ax": float(ao.get("x", 0.0)),
            "ay": float(ao.get("y", 0.0)),
            "az": float(ao.get("z", 0.0)),
        }
        self._sm_roll = 0.0
        self._sm_pitch = 0.0
        logger.info(
            "Calibration applied ax=%+.4f ay=%+.4f az=%+.4f",
            self._cal["ax"], self._cal["ay"], self._cal["az"]
        )

    def reload_mapping(self, cfg: dict) -> None:
        self._mapper.reload(cfg)
        self._alpha = float(cfg.get("smoothing_alpha", self._alpha))

    def is_available(self) -> bool:
        return self._available


def create_mpu6050(cfg: dict, mock: bool = False):
    if mock:
        drv = MockMPU6050(cfg)
        drv.init()
        return drv
    drv = RealMPU6050(cfg)
    if not drv.init():
        logger.warning("MPU unavailable, falling back to mock")
        drv = MockMPU6050(cfg)
        drv.init()
    return drv
"""Battery and ultrasonic readings. No ROS imports.

On the robot both come from the ESP32: battery voltage from the RoboClaw (or a
battery monitor) and distances from the HC-SR04P ultrasonic sensors.
"""

from abc import ABC, abstractmethod

from .esp32_backend import Esp32Link


class SensorsBackend(ABC):

  @abstractmethod
  def read_battery(self) -> float:
    """Battery voltage in volts."""

  @abstractmethod
  def read_ultrasonic(self) -> list[float | None]:
    """Distance in meters for each ultrasonic sensor, in order; None = no echo."""


class MockSensorsBackend(SensorsBackend):

  def __init__(self, battery_volts: float = 20.0, distances=(1.5,)):
    self.battery_volts = battery_volts
    self.distances = list(distances)

  def read_battery(self) -> float:
    return self.battery_volts

  def read_ultrasonic(self) -> list[float | None]:
    return list(self.distances)


class Esp32SensorsBackend(SensorsBackend):

  def __init__(self, link: Esp32Link):
    self._link = link

  def read_battery(self) -> float:
    return self._link.read_battery()

  def read_ultrasonic(self) -> list[float | None]:
    return self._link.read_ultrasonic()


def battery_fraction(volts: float, empty_volts: float, full_volts: float) -> float:
  """Rough charge left, 0..1, by linear interpolation between empty and full voltage."""
  if full_volts <= empty_volts:
    raise ValueError('full_volts must be > empty_volts')
  return max(0.0, min(1.0, (volts - empty_volts) / (full_volts - empty_volts)))

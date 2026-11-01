"""Arm joint configuration helpers. No ROS imports."""

from .joints import JointSpec


def arm_specs(names, mins, maxs, speeds, homes=None) -> list[JointSpec]:
  """Build JointSpecs from parallel lists; raises ValueError on mismatched lengths."""
  count = len(names)
  homes = list(homes) if homes else [0.0] * count
  for label, values in (('arm_min', mins), ('arm_max', maxs),
                        ('arm_max_speed', speeds), ('arm_home', homes)):
    if len(values) != count:
      raise ValueError(f'{label} has {len(values)} values for {count} joints')
  return [
    JointSpec(name, lo, hi, speed, home)
    for name, lo, hi, speed, home in zip(names, mins, maxs, speeds, homes)
  ]

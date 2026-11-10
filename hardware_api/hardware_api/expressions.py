"""Eye expressions: named presets of eye-barrel tilt. No ROS imports.

Each value is (left, right) tilt in radians; positive looks up, negative looks
down or squints. PLACEHOLDER values until the eye mechanism exists.
"""

LEFT_EYE = 'eye_left'
RIGHT_EYE = 'eye_right'

EXPRESSIONS: dict[str, tuple[float, float]] = {
  'neutral': (0.0, 0.0),
  'happy': (0.20, 0.20),
  'sad': (-0.25, -0.15),
  'surprised': (0.35, 0.35),
  'curious': (0.25, 0.05),
  'confused': (0.25, -0.15),
  'sleepy': (-0.40, -0.40),
}


def eye_targets(expression: str) -> dict[str, float]:
  """Return {eye_left: angle, eye_right: angle} for an expression name.

  Names are case-insensitive. An unknown name raises KeyError.
  """
  key = expression.strip().lower()
  if key not in EXPRESSIONS:
    raise KeyError(f"unknown expression '{expression}'; known: {sorted(EXPRESSIONS)}")
  left, right = EXPRESSIONS[key]
  return {LEFT_EYE: left, RIGHT_EYE: right}

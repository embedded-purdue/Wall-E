# hardware_api

Low-level interface to WALL-E's physical hardware: motors, sensors, servos, and the can crusher.

- **Stack:** ROS 2 (Jetson Orin Nano side) and ESP32 firmware (microcontroller side)
- **Used by:** `skills/`
- **Tests:** `tests/`

## Usage

Driving commands (`drive_node`):

| API call | ROS 2 interface |
| --- | --- |
| `drive(v, ω)` | publish `/cmd_vel` (`geometry_msgs/Twist`; only `linear.x` m/s and `angular.z` rad/s are used) |
| `stop()` | call `/hardware/stop` (`std_srvs/Trigger`) |
| `get_odometry()` | subscribe `/odom` (`nav_msgs/Odometry`, `odom` → `base_link`) |

Safety behavior:

- `/cmd_vel` must be published continuously (10 Hz or faster). If none arrives within `watchdog_timeout` (default 0.5 s), the robot stops.
- Commands are capped at `speed_cap_fraction` (default 60%) of `max_wheel_speed`. When the cap kicks in, both wheels scale together so the turning curve is kept.
- `/hardware/stop` stops the motors immediately. It does not latch: the next `/cmd_vel` drives again.

Build and run with the mock backend (no hardware needed):

```bash
colcon build --packages-select hardware_api
source install/setup.bash
ros2 launch hardware_api drive.launch.py
```

Try it:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/Twist "{linear: {x: 0.2}, angular: {z: 0.0}}"
ros2 topic echo /odom
ros2 service call /hardware/stop std_srvs/srv/Trigger
```

Robot parameters are in `config/drive.yaml`. The current values are placeholders until electrical gives real ones.

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
| `get_odometry()` | subscribe `/odom` (`nav_msgs/Odometry`, `odom` → `base_link`); the same pose is broadcast on TF (`publish_tf`, default on) |

Safety behavior:

- `/cmd_vel` must be published continuously (10 Hz or faster). If none arrives within `watchdog_timeout` (default 0.5 s), the robot stops.
- Commands are capped at `speed_cap_fraction` (default 60%) of `max_wheel_speed`. When the cap kicks in, both wheels scale together so the turning curve is kept.
- `/hardware/stop` stops the motors immediately. It does not latch: the next `/cmd_vel` drives again.

Other commands (`peripherals.launch.py`, one node each, all mock backends for now):

- `move_head(pan, tilt)`: publish `/head/cmd` (`sensor_msgs/JointState`, names `head_pan` / `head_tilt`, radians). State on `/head/state`. (`head_eyes_node`)
- `set_eyes(expression)`: publish `/eyes/expression` (`std_msgs/String`; neutral, happy, sad, surprised, curious, confused, sleepy). Last applied expression on `/eyes/state` (latched); unknown names are ignored with a warning. (`head_eyes_node`)
- `play_audio(clip)`: publish `/audio/play` (`std_msgs/String`, clip name or path). `/audio/stop` (`std_srvs/Trigger`) cuts it; `/audio/playing` (`std_msgs/Bool`, latched) shows when it is playing. (`audio_node`)
- `get_audio()`: subscribe `/audio/mic` (`std_msgs/UInt8MultiArray`): raw PCM, signed 16-bit little-endian, mono, `sample_rate` Hz, one `chunk_ms` chunk per message. (`audio_node`)
- `get_rgbd()`: subscribe `/camera/color/image_raw` (rgb8), `/camera/depth/image_raw` (32FC1, meters, NaN = no reading) and `/camera/color/camera_info`. Color and depth share a timestamp. (`camera_node`)
- `set_arm(pose)`: publish `/arm/cmd` (`sensor_msgs/JointState`, radians, names from `arm_joint_names`, partial messages are fine). State on `/arm/state`. `/arm/hold` (`std_srvs/Trigger`) stops it where it is. (`arm_node`)
- `set_gripper(close)`: call `/gripper/set` (`std_srvs/SetBool`; true closes, false opens). It returns at once. Position on `/gripper/state` (0 open, 1 closed); `/gripper/holding` (`std_msgs/Bool`, latched) is true when the fingers are stopped by an object. (`arm_node`)
- `run_crusher()`: call `/crusher/run` (`std_srvs/Trigger`). It returns `success=false` with the reason unless the chamber is closed, the hardware lock is engaged and the contents are OK. It returns as soon as the cycle starts; `/crusher/running` and `/crusher/result` (both latched) report progress. `/crusher/stop` aborts. A running cycle is aborted if any safety input goes false or cannot be read. (`crusher_node`)

Software limits on these (enforced in code, not by the hardware):

- Joint angles are clamped to the limits in `config/peripherals.yaml` and move no faster than `*_max_speed`. Non-finite angles are ignored.
- Arm, head and eye servos hold their last target when commands stop; only the crusher has a safety interlock.
- The mock crusher starts unsafe and refuses until its `mock_*` parameters are set true.
- The global `/hardware/stop` only stops driving. Whether it should also stop the arm and crusher is open (see `docs/peripherals-open-questions.md`).

Build and run with the mock backend (no hardware needed):

```bash
colcon build --packages-select hardware_api
source install/setup.bash
ros2 launch hardware_api drive.launch.py
ros2 launch hardware_api peripherals.launch.py   # head/eyes, audio, camera, arm/gripper, crusher
# options: params_file:=/path/to/params.yaml  backend:=mock  publish_tf:=false
```

Try it:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/Twist "{linear: {x: 0.2}, angular: {z: 0.0}}"
ros2 topic echo /odom
ros2 service call /hardware/stop std_srvs/srv/Trigger
```

Robot parameters are in `config/drive.yaml` and `config/peripherals.yaml`. The current values are placeholders until electrical and mechanical give real ones.

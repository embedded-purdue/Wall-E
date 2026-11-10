# Wall-E topics, services and frames

The hardware API's ROS 2 names. **The simulator (Isaac Sim) uses exactly these names, message types and frames**, so code written against them runs on the real robot and in the sim without changes.

Rule: don't rename or change anything here without telling the Sim and BT teams the same day.

Status: Nov 10, 2026, from `hardware_api` (all nodes on mock backends for now). Integration tracks the robot's position (`/odom`); in the sim, the sim publishes it under the same name.

## Driving (`drive_node`)

| Name | Kind | Type | Notes |
| --- | --- | --- | --- |
| `/cmd_vel` | topic, in | `geometry_msgs/Twist` | `linear.x` m/s, `angular.z` rad/s. Must arrive at 10 Hz or faster or the robot stops (0.5 s watchdog). Speed capped at 60%. |
| `/odom` | topic, out | `nav_msgs/Odometry` | Robot position, `odom` -> `base_link`. Same pose on TF. |
| `/hardware/stop` | service | `std_srvs/Trigger` | Stop driving now. Not latched. |

## Head and eyes (`head_eyes_node`)

| Name | Kind | Type | Notes |
| --- | --- | --- | --- |
| `/head/cmd` | topic, in | `sensor_msgs/JointState` | Joints `head_pan`, `head_tilt`, radians. |
| `/head/state` | topic, out | `sensor_msgs/JointState` | |
| `/eyes/expression` | topic, in | `std_msgs/String` | One of: neutral, happy, sad, surprised, curious, confused, sleepy. |
| `/eyes/state` | topic, out (latched) | `std_msgs/String` | Last applied expression. |

## Audio (`audio_node`)

| Name | Kind | Type | Notes |
| --- | --- | --- | --- |
| `/audio/play` | topic, in | `std_msgs/String` | Clip name or path. |
| `/audio/stop` | service | `std_srvs/Trigger` | |
| `/audio/playing` | topic, out (latched) | `std_msgs/Bool` | |
| `/audio/mic` | topic, out | `std_msgs/UInt8MultiArray` | Raw PCM, 16-bit little-endian, mono, 16000 Hz, 20 ms chunks. |

## Camera (`camera_node`)

| Name | Kind | Type | Notes |
| --- | --- | --- | --- |
| `/camera/color/image_raw` | topic, out | `sensor_msgs/Image` | rgb8 |
| `/camera/depth/image_raw` | topic, out | `sensor_msgs/Image` | 32FC1, meters, NaN = no reading. Same timestamp as color. |
| `/camera/color/camera_info` | topic, out | `sensor_msgs/CameraInfo` | |

## Arm and gripper (`arm_node`)

| Name | Kind | Type | Notes |
| --- | --- | --- | --- |
| `/arm/cmd` | topic, in | `sensor_msgs/JointState` | Joints `shoulder_pan`, `shoulder_lift`, `elbow`, `wrist` (placeholders until mech decides the arm), radians. |
| `/arm/state` | topic, out | `sensor_msgs/JointState` | |
| `/arm/hold` | service | `std_srvs/Trigger` | Stop where it is. |
| `/gripper/set` | service | `std_srvs/SetBool` | true = close, false = open. |
| `/gripper/state` | topic, out | `sensor_msgs/JointState` | `gripper`, 0 open to 1 closed. |
| `/gripper/holding` | topic, out (latched) | `std_msgs/Bool` | True when the fingers stopped on an object. |

## Crusher (`crusher_node`)

| Name | Kind | Type | Notes |
| --- | --- | --- | --- |
| `/crusher/run` | service | `std_srvs/Trigger` | Refuses unless chamber closed, lock engaged and contents OK. |
| `/crusher/stop` | service | `std_srvs/Trigger` | Abort. |
| `/crusher/running` | topic, out (latched) | `std_msgs/Bool` | |
| `/crusher/result` | topic, out (latched) | `std_msgs/String` | |

## Battery and distance (`sensors_node`)

| Name | Kind | Type | Notes |
| --- | --- | --- | --- |
| `/battery` | topic, out | `sensor_msgs/BatteryState` | `voltage` in volts, `percentage` 0 to 1 (rough). 5 Hz. For BT's `battery_sufficient`. |
| `/ultrasonic/front` | topic, out | `sensor_msgs/Range` | Meters, `+inf` = no echo. One topic per sensor (`ultrasonic_names`). For BT's `near`. |

## Frames

| Frame | Meaning |
| --- | --- |
| `odom` | Where the robot started. Object locations on the blackboard are in this frame. |
| `base_link` | Center of the robot. |
| `camera_link` | The camera. (`camera_optical_frame` for image data.) |
| `ultrasonic_front` | The front ultrasonic sensor. |

The full frame tree, joints and limits are in `hardware_api/urdf/wall_e.urdf` (v0: names are real, sizes are placeholders).

## Not decided yet

- How many ultrasonic sensors and where (one `front` placeholder for now).
- Real arm joint names and limits (waiting on mech).
- Real sizes and positions in the URDF, from mech's CAD.

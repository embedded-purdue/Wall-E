# Driving: safety limits and open questions

Status as of Oct 23, 2026, branch `feature/hw-api-driving-basics`. Covers the driving part of the hardware API (`drive`, `stop`, `get_odometry`) in `hardware_api/`.

## Safety limits of the current software

- **The software watchdog does nothing if the Jetson crashes.** It runs inside `drive_node` on the Jetson. If the Jetson freezes, crashes or loses power, nothing is left to send the stop.
- **The RoboClaw serial timeout must be enabled in hardware.** It is the only thing that stops the motors when commands stop arriving. Without it, the motors keep running their last command.
- **Stop does not latch today.** `/hardware/stop` stops the motors immediately, but the next `/cmd_vel` message drives again. A latching e-stop needs hardware (a physical button or relay that cuts motor power). This gets decided in week 5 with electrical.
- The 60% speed cap is enforced in our code. RoboClaw closed-loop modes can still go over it unless the controller is limited too (see below).

## Open questions for electrical

1. Are the drive encoders wired to the RoboClaw or to the ESP32?
2. How does the Jetson talk to the ESP32: micro-ROS or plain serial? Is the RoboClaw driven from the Jetson directly or through the ESP32?
3. Who enforces the 60% motor cap in closed-loop mode: our code only, or a limit set on the RoboClaw too?
4. Are the RoboClaw serial timeouts enabled, and with what timeout?
5. Can we read battery voltage and motor current?
6. Drivetrain numbers:
   - drive type (differential? tracks or wheels?)
   - wheel or sprocket radius
   - track width
   - gear ratio
   - encoder ticks per wheel revolution

   The values in `hardware_api/config/drive.yaml` are placeholders until we get these.

## Open questions for BT and Sim

Proposed interface. Please confirm or push back:

1. **Names:** `/cmd_vel` (`geometry_msgs/Twist`; only `linear.x` m/s and `angular.z` rad/s are read), `/odom` (`nav_msgs/Odometry`), `/hardware/stop` (`std_srvs/Trigger`), and TF `odom` → `base_link`.
2. **Watchdog:** `/cmd_vel` must be published continuously at 10 Hz or faster. If no message arrives for 0.5 s, the robot stops. A single one-shot message moves it for at most 0.5 s.
3. **Speed cap:** commands are capped at 60% of max wheel speed, and turn rate is capped to match. Commands over the cap are scaled down silently, with no error. The turning curve is kept.
4. **Stop:** `/hardware/stop` does not latch. The next `/cmd_vel` drives again.
5. **Odometry:** it starts at zero wherever `drive_node` starts. Only x, y, heading and forward/turn speed are filled in. Covariances are left at zero.
6. **TF:** `drive_node` broadcasts `odom` → `base_link` by default. If the simulator publishes that transform itself, run with `publish_tf: false`.

**For Sim:** does the simulator *replace* `drive_node` (consuming `/cmd_vel` directly), or sit *under* it as a drive backend? If it replaces the node, the simulator must also provide `/hardware/stop` and the same 0.5 s watchdog, so behavior trees act the same in sim and on the robot.

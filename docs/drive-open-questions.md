# Driving: safety limits and open questions

Status as of Nov 1, 2026 (first written Oct 23 on `feature/hw-api-driving-basics`). Covers the driving part of the hardware API (`drive`, `stop`, `get_odometry`) in `hardware_api/`.

## Safety limits of the current software

- **The software watchdog does nothing if the Jetson crashes.** It runs inside `drive_node` on the Jetson. If the Jetson freezes, crashes or loses power, nothing is left to send the stop.
- **The ESP32 must stop the motors on its own when commands stop.** Electrical agreed to a software stop if the Jetson or UART link goes down; the timeout we propose is 500 ms (docs/esp32-protocol.md). The RoboClaw serial timeout should also be on, in case the ESP32 itself crashes.
- **Stop does not latch today.** `/hardware/stop` stops the motors immediately, but the next `/cmd_vel` message drives again. A latching e-stop needs hardware (a physical button or relay that cuts motor power). Electrical's plan has limit switches but no e-stop button yet; this gets decided in week 5.
- The 60% speed cap is enforced in our code. RoboClaw closed-loop modes can still go over it unless the controller is limited too (see below).

## Answered by electrical (Oct 21, shared Oct 31)

- Encoders are wired to the RoboClaws.
- The Jetson talks to an ESP32-S3 over UART with plain serial (not micro-ROS). The ESP32 drives the RoboClaws (one Packet Serial bus) and the Maestro. Electrical owns the ESP32 code.
- Battery voltage will come from the drive RoboClaws or a separate monitor, reported by the ESP32.
- Failsafe: limit switches plus a software stop if the Jetson or UART goes down.

## Still open for electrical

1. Who enforces the 60% cap on the Yellow Jacket (arm, crusher) motors in closed loop: a max PWM limit on the RoboClaw? (The Saturn tread motors don't need this cap; our 60% drive cap is a conservative choice for testing.)
2. Agree on the message format in `docs/esp32-protocol.md`, including the 500 ms stop-on-silence timeout.
3. Drivetrain numbers: sprocket radius, track width (distance between tread centers), encoder counts per wheel turn (Saturn 188:1 per the BOM). The values in `hardware_api/config/drive.yaml` are placeholders until we get these.
4. Is there an emergency stop button that cuts motor power?

## Open questions for BT and Sim

Proposed interface. Please confirm or push back:

1. **Names:** `/cmd_vel` (`geometry_msgs/Twist`; only `linear.x` m/s and `angular.z` rad/s are read), `/odom` (`nav_msgs/Odometry`), `/hardware/stop` (`std_srvs/Trigger`), and TF `odom` → `base_link`.
2. **Watchdog:** `/cmd_vel` must be published continuously at 10 Hz or faster. If no message arrives for 0.5 s, the robot stops. A single one-shot message moves it for at most 0.5 s.
3. **Speed cap:** commands are capped at 60% of max wheel speed, and turn rate is capped to match. Commands over the cap are scaled down silently, with no error. The turning curve is kept.
4. **Stop:** `/hardware/stop` does not latch. The next `/cmd_vel` drives again.
5. **Odometry:** it starts at zero wherever `drive_node` starts. Only x, y, heading and forward/turn speed are filled in. Covariances are left at zero.
6. **TF:** `drive_node` broadcasts `odom` → `base_link` by default. If the simulator publishes that transform itself, run with `publish_tf: false`.

**For Sim:** does the simulator *replace* `drive_node` (consuming `/cmd_vel` directly), or sit *under* it as a drive backend? If it replaces the node, the simulator must also provide `/hardware/stop` and the same 0.5 s watchdog, so behavior trees act the same in sim and on the robot.

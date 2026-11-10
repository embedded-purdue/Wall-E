# Jetson to ESP32 message format (draft v0)

Status: **draft for electrical to review**, Nov 1, 2026. Nothing here is final until electrical agrees.

The Jetson (our ROS 2 code) talks to the ESP32-S3 (electrical's firmware) over UART. The ESP32 turns these messages into RoboClaw and Maestro commands. This file covers driving and (draft, Nov 10) the servos on the Maestro. The arm and crusher motors get added the same way later.

## Link

- UART, 115200 baud, 8N1, 3.3 V logic on both sides. Ground shared between Jetson and ESP32.
- One ASCII line per message, ending in `\n` (the ESP32 should also accept `\r\n`).
- The Jetson sends one command and waits for exactly one reply line before sending the next (up to 50 ms).
- Plain text so anyone can test it by typing into a serial monitor.

## Messages

| Jetson sends | ESP32 replies | Meaning |
| --- | --- | --- |
| `D <left_rpm> <right_rpm>` | `OK D` | Set tread speeds with RoboClaw closed-loop speed control. Wheel RPM, 2 decimals, positive = forward for both sides. |
| `S` | `OK S` | Stop all drive motors now. |
| `H` | `OK H` | Heartbeat when there is nothing else to send. |
| `E` | `E <left> <right>` | Cumulative encoder counts as the RoboClaw reports them (signed integers). |
| `B` | `B <volts>` | Battery voltage, for example `B 19.85`. |
| `U` | `U <m> [<m> ...]` | Ultrasonic distances in meters, one per HC-SR04P in a fixed order, `-1` = no echo. For example `U 0.42 1.80`. (draft, Nov 10) |
| anything wrong | `ERR <reason>` | Command not understood or refused, for example `ERR bad_args`. |
| (nothing) | `READY` | Sent once after the ESP32 boots, with motors stopped. |

Example session:

```
ESP32 -> READY
Jetson -> D 10.00 10.00
ESP32 -> OK D
Jetson -> E
ESP32 -> E 1365 1362
Jetson -> S
ESP32 -> OK S
```

## Servos (draft, Nov 10)

Electrical has servo control working on the Maestro (Nov 8). These messages let our code move a servo through the ESP32.

| Jetson sends | ESP32 replies | Meaning |
| --- | --- | --- |
| `P <channel> <us>` | `OK P` | Move the servo on Maestro channel `<channel>` to pulse width `<us>` microseconds (for example `P 0 1500` = center). The ESP32 sends the Maestro "set target" command (the Maestro counts in quarter-microseconds, so target = us x 4). |
| `Q <channel>` | `Q <channel> <us>` | Where the Maestro says that servo is right now (Maestro "get position"), in microseconds. |
| `P` out of range | `ERR out_of_range` | The pulse width is outside that channel's safe min/max (see below). Nothing moves. |

Rules:

1. **Safe limits live in the firmware too.** Each channel gets a min and max pulse width so a servo can never be driven into its hard stop, even if our code sends a bad number. We clamp in our code as well.
2. **Servos hold their position** when messages stop. Stop-on-silence applies to the drive motors only (a head servo going limp could drop the head).
3. **Speed and acceleration** limits are set once in the Maestro's settings (Maestro Control Center), not sent every time.

Channel map (electrical to fill in):

| Channel | Servo | Min us | Center us | Max us |
| --- | --- | --- | --- | --- |
| ? | head pan | | | |
| ? | head tilt | | | |
| ? | left eye | | | |
| ? | right eye | | | |
| ? | gripper (if it is a servo) | | | |

Our side: `move_head`, `set_eyes` and `set_gripper` turn angles and expressions into these `P` messages (`hardware_api/servo.py`). The channel numbers and pulse widths in `config/esp32.yaml` are placeholders until this map is filled in.

## Safety rules we are asking the firmware to follow

1. **Boot stopped.** Motors stay off until the first `D`.
2. **Stop on silence.** Every valid line counts as a heartbeat. If no valid line arrives for **500 ms**, stop all motors and reply to the next command normally. The Jetson sends at 50 Hz, so 500 ms is 25 missed messages.
3. **Also enable the RoboClaw serial timeout**, so the motors stop if the ESP32 itself crashes.
4. **Speed limit lives in both places.** Our code caps speed; the ESP32 should also refuse or clamp RPM above a maximum electrical picks.

## Mapping to Sloan's RoboClaw code

| Message | RoboClaw function it should call |
| --- | --- |
| `D` | "command a specific motor RPM" on M1 (left) and M2 (right), converted to encoder units |
| `S` | stop, both motors |
| `E` | "read quadrature encoder counts for M1 and M2" |
| `B` | RoboClaw main battery voltage read (or the power team's monitor) |

## Questions for electrical

1. Which RoboClaw channel is the left tread and which is the right, and does one side need its direction flipped? (We'd like the ESP32 to hide that, so positive is always forward.)
2. Is 115200 baud fine on the Jetson link?
3. Encoder counts per wheel turn for the drive motors (the bench test script measures this).
4. Is 500 ms the right stop-on-silence timeout?
5. Fill in the servo channel map above, and confirm whether the gripper is a servo or a motor. A plain servo can't tell us if it's holding something: can we add a sensor (servo current or a switch in the fingers)?
8. How many ultrasonic sensors, in what order, and where are they mounted? Is `U` OK?
6. Are the `P` / `Q` servo messages OK, or would you rather use a different format?
7. What did the first drivetrain motor test show (speed reached, encoder counts per turn, any problems)?

## Trying it

- No hardware: `python3 -m hardware_api.bench_drive --fake`
- Real ESP32 from a laptop (USB-to-UART cable or the ESP32's USB port): `python3 -m hardware_api.bench_drive --port /dev/ttyUSB0`
- Full ROS 2 node: `ros2 launch hardware_api drive.launch.py backend:=esp32` with `esp32_port` set in the params file.
- Everything on the ESP32 (drive, head/eyes, gripper, battery, ultrasonics) sharing the one serial port: `ros2 launch hardware_api esp32.launch.py` (settings in `config/esp32.yaml`). These nodes must run in one process because there is only one UART.

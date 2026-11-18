# Jetson to ESP32 message format (draft v0)

Status: **draft for electrical to review**, Nov 1, 2026. Nothing here is final until electrical agrees. Electrical's answers from Nov 15 are recorded under "Answers from electrical" below.

The Jetson (our ROS 2 code) talks to the ESP32-S3 (electrical's firmware) over UART. The ESP32 turns these messages into RoboClaw and Maestro commands. This file covers driving, (draft, Nov 10) the servos on the Maestro, and (draft, Nov 18) the arm motors, the crusher motor and the switch inputs.

## Link

- UART, 115200 baud (OK'd by electrical, Nov 15), 8N1, 3.3 V logic on both sides. Ground shared between Jetson and ESP32.
- One ASCII line per message, ending in `\n` (the ESP32 should also accept `\r\n`).
- The Jetson sends one command and waits for exactly one reply line before sending the next (up to 50 ms).
- Plain text so anyone can test it by typing into a serial monitor.

## Messages

| Jetson sends | ESP32 replies | Meaning |
| --- | --- | --- |
| `D <left_rpm> <right_rpm>` | `OK D` | Set tread speeds with RoboClaw closed-loop speed control. Wheel RPM, 2 decimals, positive = forward for both sides. |
| `R <left_revs> <right_revs>` | `OK R` | Turn each tread sprocket this many output-shaft revolutions from where it is now, then stop (proposed by electrical, Nov 15). Decimals allowed, 3 places; positive = forward. See below. |
| `S` | `OK S` | Stop all drive motors now. |
| `H` | `OK H` | Heartbeat when there is nothing else to send. |
| `E` | `E <left> <right>` | Cumulative encoder counts as the RoboClaw reports them (signed integers). |
| `B` | `B <volts>` | Battery voltage, for example `B 19.85`. |
| `U` | `U <m> [<m> ...]` | Ultrasonic distances in meters, one per HC-SR04P in a fixed order, `-1` = no echo. For example `U 0.42 1.80`. (draft, Nov 10) |
| `A <counts> [<counts> ...]` | `OK A` | Move each arm motor to an absolute encoder count (draft, Nov 18, see "Arm and crusher"). |
| `J` | `J <counts> [<counts> ...]` | Arm motor encoder counts, same order as `A`. |
| `C <percent>` | `OK C` | Run the crusher motor at this duty, 0 to 100 (`C 0` = stop). `ERR interlock` if a crusher switch is open. |
| `I` | `I <0/1> <0/1> <0/1> <0/1>` | Switch inputs: chamber closed, lock engaged, contents OK, gripper finger switch (1 = closed/pressed). |
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

## Drive a set distance: `R` (electrical, Nov 15)

Electrical (John) proposed this. `R 2.5 2.5` turns both sprockets 2.5 revolutions forward and then stops; `R 0.5 -0.5` spins in place.

- The firmware uses the encoders and the RoboClaw's velocity PID to get there. There are **5281.1 encoder counts per sprocket revolution**, so the firmware's target is `revs x 5281.1` counts from the current position.
- The ESP32 answers `OK R` right away, when the move starts, not when it ends. The Jetson watches `E` (encoder counts) to see when both sides have arrived.
- A new `D`, `R` or `S` replaces a move that is still running.
- Stop-on-silence still applies during a long move, so the Jetson keeps sending `H` (or `E`) while it waits.

Open questions for electrical: what speed does `R` use, and can the Jetson set it? Is there an accuracy window where the firmware counts a move as done?

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

## Arm and crusher (draft, Nov 18)

The arm joints and the crusher are DC motors on RoboClaws, like the treads. The arm's motion is planned on the Jetson (Shrey's decision): our code moves each joint a small step at a time at a safe speed, so the ESP32 only ever gets "go to this position" commands and never plans a path itself.

| Jetson sends | ESP32 replies | Meaning |
| --- | --- | --- |
| `A 0 -120 840 0` | `OK A` | Hold each arm motor at this absolute encoder count, using the RoboClaw's position PID. One value per arm motor, always all of them, integers. |
| `J` | `J 0 -118 836 0` | Where the arm encoders are now. |
| `C 60` | `OK C` | Crusher motor at 60% duty, one direction. `C 0` stops it. |
| `I` | `I 1 1 1 0` | The four switch inputs, in this fixed order: chamber closed, lock engaged, contents OK, gripper finger switch. |

Rules:

1. **Arm encoders read 0 at boot.** The firmware zeroes them on power-up, so the arm must be at its home pose then. Our code turns counts into joint angles (`arm_counts_per_rad` in `config/esp32.yaml`).
2. **The arm holds on silence.** Stop-on-silence stops the treads and the crusher, not the arm: an arm motor going limp could drop the arm. `S` also stops the crusher but leaves the arm holding.
3. **Crusher interlock in the firmware too.** `C` with a duty above 0 is refused with `ERR interlock` unless chamber closed, lock engaged and contents OK all read 1, and the crusher stops at once if any of them opens while it runs. Our code checks the same switches first.
4. Our code caps the crusher at 60% duty for now; the firmware should cap it too.

Open questions for electrical: which RoboClaw and channel is each arm motor and the crusher, and in what order should `A` list the arm motors? How many counts per joint revolution (gearing after the motor)? Should the arm be homed with limit switches instead of "power up at home"? Which ESP32 pins are the four switches, and are they active-low? Is the gripper finger switch going in?

## Safety rules we are asking the firmware to follow

1. **Boot stopped.** Motors stay off until the first `D`.
2. **Stop on silence.** Every valid line counts as a heartbeat. If no valid line arrives for **500 ms**, stop all motors and reply to the next command normally. The Jetson sends at 50 Hz, so 500 ms is 25 missed messages.
3. **Also enable the RoboClaw serial timeout**, so the motors stop if the ESP32 itself crashes.
4. **Speed limit lives in both places.** Our code caps speed; the ESP32 should also refuse or clamp RPM above a maximum electrical picks.

## Mapping to Sloan's RoboClaw code

| Message | RoboClaw function it should call |
| --- | --- |
| `D` | "command a specific motor RPM" on M1 (left) and M2 (right), converted to encoder units |
| `R` | RoboClaw position/distance command for M1 and M2, target = revs x 5281.1 counts |
| `S` | stop, both motors |
| `E` | "read quadrature encoder counts for M1 and M2" |
| `B` | RoboClaw main battery voltage read (or the power team's monitor) |
| `A` | RoboClaw position command for each arm motor (absolute encoder target) |
| `J` | "read quadrature encoder counts" for the arm motors |
| `C` | RoboClaw duty command for the crusher motor (0 = stop) |

## Answers from electrical (John, Nov 15)

- **Baud:** 115200 is fine.
- **Stop-on-silence:** 500 ms agreed, and the RoboClaw serial timeout will be turned on as well.
- **Servo messages:** `P <channel> <position>` is OK, with the position in microseconds.
- **Encoders:** 5281.1 counts per sprocket revolution.
- **New message:** `R <left_revs> <right_revs>` (see above).

## Still open

1. Which RoboClaw channel is the left tread and which is the right, and does one side need its direction flipped? (We'd like the ESP32 to hide that, so positive is always forward.) Still TBD as of Nov 15.
2. What speed does `R` use, and when does it count a move as done?
3. Fill in the servo channel map above, and confirm whether the gripper is a servo or a motor. A plain servo can't tell us if it's holding something: can we add a sensor (servo current or a switch in the fingers)?
4. Is `Q` (read a servo's position) OK too?
5. How many ultrasonic sensors, in what order, and where are they mounted? Is `U` OK?
6. What did the first drivetrain motor test show (speed reached, any problems)?

## Trying it

- No hardware: `python3 -m hardware_api.bench_drive --fake`
- Real ESP32 from a laptop (USB-to-UART cable or the ESP32's USB port): `python3 -m hardware_api.bench_drive --port /dev/ttyUSB0`
- Full ROS 2 node: `ros2 launch hardware_api drive.launch.py backend:=esp32` with `esp32_port` set in the params file.
- Arm, crusher, a servo or the switches, one command at a time: `python3 -m hardware_api.bench_esp32 --port /dev/ttyUSB0 inputs` (or `--fake`; run with `--help` for the rest).
- Everything on the ESP32 (drive, head/eyes, arm, gripper, crusher, battery, ultrasonics) sharing the one serial port: `ros2 launch hardware_api esp32.launch.py` (settings in `config/esp32.yaml`). These nodes must run in one process because there is only one UART.

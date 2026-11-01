# Head, eyes, audio, camera, arm, gripper, crusher: open questions

Status as of Nov 1, 2026. These commands exist in `hardware_api/` against mock backends only. Nothing here has run on the robot, and the ROS nodes have not been built yet. Every number in `config/peripherals.yaml` is a placeholder.

## What the electrical notes say so far

- Servos run on a Pololu Maestro (12 channels). Head pan and tilt are servos; the eyes are probably one micro servo each (SG90-class).
- Motors run on RoboClaw controllers. In the notes' example wiring the ESP32 drives the RoboClaw over UART (packet serial, 38400 baud, address 0x80), so the Jetson may reach the RoboClaw only through the ESP32.
- The arm shoulder may be a DC gear motor or stepper, possibly on a linear track with limit switches. Fingers may be hydraulic. Absolute encoders (AS5600 / MT6826S) for the joints are being considered.
- The notes describe a CSI camera on the Jetson. That is color only; our brief says RGB-D.

## Questions for electrical

1. Servo channel map and total servo count (the Maestro handles 12, expected 15 to 20). Which channels are head pan, head tilt and each eye?
2. Pulse range and safe angle range for each head and eye servo.
3. Camera model. Does it give depth? If not, `get_rgbd` publishes NaN depth and depth-based skills (`navigate_to`, `is_at`) need another sensor.
4. Microphone and speaker hardware, and where they connect (Jetson or ESP32).
5. How do the Jetson and ESP32 talk (serial or micro-ROS), and is the Maestro on the Jetson's USB or behind the ESP32? This decides every real backend.
6. Arm: number of joints, limits, gear ratios, and what drives each joint. Gripper: how does it sense that it is holding something?
7. Crusher: what are the physical safety signals (door, lock, contents) and can the code read them? These map to `chamber_closed`, `hardware_lock_engaged` and `contents_ok`.

## Decisions for the team

1. Should `/hardware/stop` also stop the arm, gripper and crusher, or should each have its own stop (as now)? A latching e-stop needs hardware (week 5).
2. Eye expressions are tilt presets (`expressions.py`). If the eyes turn out to be displays or LEDs, only `eye_targets` and the eye backend change.
3. `play_audio` takes a clip name or path. Confirm with NLP how TTS audio will reach it (file path, or a stream).

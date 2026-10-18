# WALL-E

The WALL-E project builds a life-sized robotic platform that brings the movie character to life while giving the concept a real environmental purpose. Powered by an NVIDIA Jetson Orin Nano, the robot perceives and responds to its surroundings, interprets voice commands, navigates autonomously, and identifies and collects trash through computer vision and machine learning—while displaying expressive behaviors that give it a sense of personality.

A signature feature is an onboard can crusher inspired directly by WALL-E's trash-compacting function in the film. Beyond recreating an iconic character, the project explores how robotics and AI can make environmental cleanup more interactive, autonomous, and impactful.

## Repository Structure

```
Wall-E/
├── hardware_api/        # ROS 2 + ESP32 interface to motors, sensors, can crusher
├── skills/              # Reusable robot capabilities built on hardware_api
├── behavior_tree/
│   ├── nlp/             # Voice/text command interpretation
│   └── bt_construct/    # Behavior tree construction and execution (uses skills)
├── virtual_sim/         # Python simulation for testing without hardware
└── docs/                # Design docs and diagrams
```

Each component has its own `README.md` and a `tests/` folder.

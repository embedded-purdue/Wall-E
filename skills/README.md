# skills

Layer 1: the BT skills, built on `hardware_api/`. Behavior trees call these and nothing lower.

- **Stack:** ROS 2 (Python). Interfaces are in `wall_e_interfaces/`.
- **Used by:** `behavior_tree/`
- **Tests:** `tests/` (plain pytest, no ROS needed)

**Status (Nov 3, 2026):** every skill is a **mock** (`mock_skills_node`). The real simple versions replace it behind the same actions and services, so trees written against the mocks will not change.

## Interfaces

Action skills are ROS 2 actions; conditions are services. All live under `/skills/`.

| Skill | Interface | Goal / request | Result / response |
| --- | --- | --- | --- |
| `search_for(object, hint?)` | action `SearchFor` | `object`, `hint` | `location` (write to `<object>.location`) |
| `navigate_to(target)` | action `NavigateTo` | `target`, `location`, `stop_distance` | |
| `say(text, emotion?)` | action `Say` | `text`, `emotion` | |
| `express(emotion)` | action `Express` | `emotion` | |
| `look_at(target)` | action `LookAt` | `target`, `location` | |
| `move_arm(pose)` | action `MoveArm` | `pose_name` or `target` | |
| `grab(object)` | action `Grab` | `object`, `location` | |
| `release(target?)` | action `Release` | `target`, `location` | |
| `crush(object)` | action `Crush` | `object` | |
| `is_visible(object)` | service `IsVisible` | `object` | `visible`, `location` |
| `is_at(target)` | service `IsAt` | `target`, `location`, `threshold` | `at`, `distance` |

Conventions:

- **Status:** an action succeeds (`SUCCEEDED`, `result.success = true`) or fails (`ABORTED`, `result.success = false`, `result.reason` set). Canceling gives `CANCELED`, reason `canceled`. While it runs, the BT leaf returns `RUNNING`.
- **Blackboard:** skills do not touch the blackboard. The BT leaf writes result fields to it (e.g. `SearchFor.location` → `can.location`) and passes them back in goals (`NavigateTo.location`). Locations are `geometry_msgs/PointStamped` in the `odom` frame; an empty `header.frame_id` means "not given".
- **Optional fields:** `""` for strings, `0` for numbers (`timeout_s`, `stop_distance`, `threshold` then use defaults).
- **Every action has `timeout_s`** and fails with `timeout` if it runs out.

Failure reasons:

| Reason | When |
| --- | --- |
| `invalid_goal` | a required field is empty |
| `not_found` | `search_for` gave up |
| `unknown_target` | `navigate_to` has no location and the target is not a found object or known spot |
| `not_visible` | `look_at` target is not in view |
| `unknown_emotion` | `say` / `express` emotion is not one of: neutral, happy, sad, surprised, curious, confused, sleepy |
| `unknown_pose` | `move_arm` pose is not one of: rest, wave, grab_front, crush_drop |
| `out_of_reach` | `grab` with a location Wall-E is not at |
| `already_holding` | `grab` with something already in the hand |
| `not_holding` | `release` / `crush` with an empty hand, or `grab` closed on nothing |
| `wrong_object` | `crush(x)` while holding something else |
| `crusher_unsafe` | the crusher's safety check refused |
| `timeout`, `canceled` | as named |
| `mock_failure` | mocks only: forced with `mock_failing_skills` |

## Mock behavior

The mocks keep a little pretend state so trees behave sensibly:

- `is_visible(x)` is false until `search_for(x)` succeeds (or `x` is in `mock_visible_objects`). Found objects are at `mock_object_location`.
- `navigate_to(x)` makes `is_at(x)` true.
- `grab` with no location assumes the known spot in front of Wall-E. With a location, Wall-E must be at it.
- `crush` and `release` need something held. A crushed object is gone.
- Every action takes `mock_delay_s` and publishes feedback while it runs.

Force failures to test fallback branches (live, no restart):

```bash
ros2 param set /mock_skills_node mock_missing_objects "['ball']"   # search_for(ball) -> not_found
ros2 param set /mock_skills_node mock_failing_skills "['grab']"    # grab -> mock_failure
ros2 param set /mock_skills_node mock_crusher_safe false           # crush -> crusher_unsafe
ros2 service call /skills/mock/reset std_srvs/srv/Trigger          # forget found/held/reached
```

## Build and run

```bash
colcon build --packages-select wall_e_interfaces skills
source install/setup.bash
ros2 launch skills mock_skills.launch.py
```

Try it:

```bash
ros2 action send_goal --feedback /skills/search_for wall_e_interfaces/action/SearchFor "{object: can}"
ros2 service call /skills/is_visible wall_e_interfaces/srv/IsVisible "{object: can}"
ros2 action send_goal /skills/navigate_to wall_e_interfaces/action/NavigateTo \
  "{target: can, location: {header: {frame_id: odom}, point: {x: 1.5}}}"
ros2 action send_goal /skills/grab wall_e_interfaces/action/Grab "{object: can}"
ros2 action send_goal /skills/crush wall_e_interfaces/action/Crush "{object: can}"
```

Tests: `cd skills && python -m pytest`.

## Code layout

- `skills/hardware.py`: `HardwareClient`, the Layer 2 commands as the skills see them. Skills use only this.
- `skills/ros_hardware.py`: `HardwareClient` over the `hardware_api` topics and services (robot and sim).
- `skills/fake_hardware.py`: in-memory `HardwareClient` for unit tests.
- `skills/mock_skills.py` + `mock_skills_node.py`: the mocks.

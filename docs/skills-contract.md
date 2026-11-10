# Skills contract: proposals for the Nov 11 software meeting

Status: **proposal from Integration**, to agree with BT Construction, NLP and Sim. Once agreed, this file is the source of truth, and any change gets announced to BT and Sim the same day.

The skill inputs and outputs themselves are in `skills/README.md` and `wall_e_interfaces/` (Sneha's `feature/bt-skills` branch). The XML vocabulary NLP generates is in `behavior_tree/bt_construct/wall_e.yaml` and `schema.md` (Monish's branches). This file settles where those disagree.

## 1. Emotion labels

**Proposal:** everyone uses these 7: `neutral`, `happy`, `sad`, `surprised`, `curious`, `confused`, `sleepy`.

- The eyes, `say` and `express` already accept exactly these.
- NLP's current 5 (happy, curious, sad, surprised, confused) are all in the list; NLP adds `neutral` and `sleepy`.
- Josh confirmed `sleepy` replaces `tired` (Nov 8).
- Anything else makes `say` / `express` fail with `unknown_emotion`.

## 2. Blackboard

**Proposal:** skills never touch the blackboard. They return data in their result, and the BT node writes it.

- `SearchFor(object)` result `location` -> BT writes `<object>.location`.
- `IsVisible(object)` success -> BT writes `<object>.location`.
- `NavigateTo(target)`, `LookAt(target)`, `Grab(object)`, `IsAt(target)` -> BT reads `<name>.location` and sends it in the goal.
- Locations are `geometry_msgs/PointStamped` in the `odom` frame. Empty `frame_id` = "not given".
- `user` and named places (`home`) come from BT's world state, not from a search.

Vatsal's `bt_construct` runner already works this way. NLP's `schema.md` says "SearchFor writes", which is the same result; update its wording.

## 3. MoveArm input

NLP's XML has one port, `pose`. The `MoveArm` action has `pose_name` or `target`.

**Proposal (BT node does the mapping):**

- If `pose` is a named pose (`rest`, `wave`, `grab_front`, `crush_drop`), send it as `pose_name`.
- Otherwise treat it as a name and send `<pose>.location` from the blackboard as `target` (e.g. `pose="user"` reaches toward the user).
- If neither works, the node fails with `unknown_pose`.
- NLP training data uses `pose="raised"`, which is not a pose: either remove it, or we add `raised` as a named pose. Decide at the meeting.

## 4. Stop

**Proposal:** there is no Stop skill and the LLM never generates one. Stopping is a safety function outside the trees:

- `/hardware/stop` stops driving immediately (exists now).
- The drive watchdog stops the robot if commands stop arriving (exists now), and the ESP32 stops on link loss.
- The main tree (Josh) calls stop through its own node, not through a generated subtree.

## 5. Josh's main tree nodes

BT asked for: `near`, `stop`, `is_quiet`, `battery_sufficient`, `snooze`. Proposed owners, to confirm:

| Node | Needs | Proposed owner |
| --- | --- | --- |
| `stop` | `/hardware/stop` | BT node calls the existing service |
| `near` | `/ultrasonic/front` (`sensor_msgs/Range`, from `sensors_node`) | Integration publishes it (done, mock + ESP32); BT writes the condition |
| `battery_sufficient` | `/battery` (`sensor_msgs/BatteryState`, from `sensors_node`) | Integration publishes it (done, mock + ESP32); BT writes the condition |
| `is_quiet` | mic input `/audio/mic` | NLP (they own speech) |
| `snooze` | `express(sleepy)` + stop driving | BT, built from existing skills |

## 6. Still to agree

- Who turns NLP's text reply into audio (text-to-speech), and the audio format `say` receives.
- Who builds the URDF from mech's CAD, and when Sim gets it.
- Which branch everyone builds on until Shrey merges to main.

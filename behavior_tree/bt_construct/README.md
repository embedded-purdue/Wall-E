# bt_construct

Runs Wall-E behavior trees. Give it a BehaviorTree.CPP XML file in the schema v1
format and it ticks the tree, calling the real skills through their ROS 2 actions
and services (`/skills/<name>`, from `wall_e_interfaces`).

For now it runs against `mock_skills_node` from the `skills` package, so the tree
logic can be tested without the robot.

**Stack: C++** (this README used to say Python). Schema v1 trees are BehaviorTree.CPP
XML, and BehaviorTree.CPP is the library that executes that format; the Python BT
libraries (e.g. py_trees) use their own tree format. Tree *generation* in `nlp/`
stays Python, so only the executor is C++.

## Build and run

From the root of a ROS 2 Jazzy workspace that has this repo in `src/`:

```bash
colcon build --packages-select wall_e_interfaces skills bt_construct
source install/setup.bash

# terminal 1: fake skills
ros2 run skills mock_skills_node

# terminal 2: run a tree
ros2 run bt_construct run_tree install/bt_construct/share/bt_construct/trees/find_and_crush.xml
```

Every node prints its status changes as it runs. The last line is
`tree finished: SUCCESS` or `tree finished: FAILURE`. Exit codes:

| code | meaning |
|------|---------|
| 0 | tree succeeded |
| 1 | tree failed (the failing skill's `reason` is logged), or Ctrl-C |
| 2 | bad arguments, or the XML couldn't be loaded (e.g. it uses a node that isn't implemented yet) |

`--tick-ms N` changes how often the tree is ticked (default 100).

The mock's parameters set up different situations, for example:

```bash
ros2 run skills mock_skills_node --ros-args -p mock_missing_objects:="['can']"   # SearchFor fails: not_found
ros2 run skills mock_skills_node --ros-args -p mock_crusher_safe:=false          # Crush fails: crusher_unsafe
ros2 run skills mock_skills_node --ros-args -p mock_visible_objects:="['can']"   # IsVisible succeeds, so SearchFor is skipped
```

## Tests

```bash
python -m pytest src/Wall-E/behavior_tree/bt_construct/tests
```

Each test starts its own `mock_skills_node` on a random `ROS_DOMAIN_ID`, runs a tree
from `trees/` and checks the exit code and output. They take about 10 s in total.

## What's implemented

| node | type | ROS name | blackboard |
|------|------|----------|------------|
| `SearchFor(object, hint?)` | action | `/skills/search_for` | writes `<object>.location` |
| `NavigateTo(target)` | action | `/skills/navigate_to` | reads `<target>.location` |
| `Grab(object)` | action | `/skills/grab` | reads `<object>.location` |
| `Crush(object)` | action | `/skills/crush` | |
| `IsVisible(object)` | condition | `/skills/is_visible` | writes `<object>.location` if visible |

**Not done yet:** `Say`, `Express`, `LookAt`, `MoveArm`, `Release`, `IsAt`. A tree
that uses one of them fails to load with exit code 2.

## How it works

- `include/bt_construct/skill_action.hpp`: `SkillAction<ActionT>`, the base class for
  every action node. `onStart` sends the goal, `onRunning` reports RUNNING until the
  result comes back, and `onHalted` cancels the goal (when a Fallback moves on, or on
  Ctrl-C). A skill that returns `success=false` makes the node fail and logs its `reason`.
- `src/skill_nodes.cpp`: one small class per skill that fills in the goal from the
  node's ports, plus `registerSkillNodes()`, which maps XML names to classes and ROS names.
- `src/run_tree.cpp`: the executable. It ticks the tree on the main thread and spins
  ROS on a second thread, where the action and service responses arrive.

Conditions such as `IsVisible` must answer within a single tick, so they block on the
service for up to 1 s instead of returning RUNNING.

## Adding a skill node

Take `Say` as an example:

1. In `src/skill_nodes.cpp`, include `wall_e_interfaces/action/say.hpp` and add a class:

   ```cpp
   class Say : public SkillAction<action::Say> {
    public:
     using SkillAction::SkillAction;
     static BT::PortsList providedPorts() {
       return {BT::InputPort<std::string>("text"), BT::InputPort<std::string>("emotion", "", "")};
     }
    protected:
     bool makeGoal(Goal& goal) override {
       if (!requireString(*this, logger(), "text", goal.text)) return false;
       goal.emotion = getInput<std::string>("emotion").value_or("");
       return true;
     }
   };
   ```

2. Register it in `registerSkillNodes()`:
   `registerSkill<Say>(factory, "Say", node, "/skills/say");`
3. Add a tree under `trees/` and a test in `tests/test_run_tree.py` that uses it.

The port names must match `wall_e.yaml` exactly, since the LLM-generated trees use them.

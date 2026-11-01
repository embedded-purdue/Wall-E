# Wall-E NLP → BT contract v1 (proposal)

Status: aligned in this branch, **pending BT Construction and Integration approval**.
This does not register executable skills or claim agreement with another team.

`wall_e.yaml` in this folder is the single XML vocabulary. NLP builds its prompt
from it; the existing `akshat-work/model/bt_validator.py` validates against it.
The old `akshat-work/model/wall_e.yaml` path is a symlink for notebook compatibility.
`allowed_primitives.yaml` is the upstream robot vocabulary, not Wall-E's.

## Routing

The main model always returns exactly `type`, `reply`, `emotion`:

```json
{"type": "task", "reply": null, "emotion": null}
```

Types: `task`, `cannot_do`, `conversation`, `unclear`. Reply is a string or null.
Emotion is null or `happy`, `curious`, `sad`, `surprised`, `confused` (provisional
until Integration agrees). Non-task requests produce no tree. For a task, code
retrieves an example; a separate model call generates XML. Both calls may use
Llama-3.2-1B, with separate task-specific adapters later.

## XML

One `<root BTCPP_format="4" main_tree_to_execute="MainTree">`, containing one
`<BehaviorTree ID="MainTree">`, containing exactly one top-level node. XML is
case-sensitive. Use PascalCase leaf names and the exact YAML parameter names.
`<Action ID="SearchFor" .../>` and `<Condition ID="IsVisible" .../>` are also
accepted; an `IsVisible` condition must never be an `Action`.

```xml
<root BTCPP_format="4" main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Sequence>
      <Fallback>
        <IsVisible object="ball"/>
        <SearchFor object="ball"/>
      </Fallback>
      <NavigateTo target="ball"/>
    </Sequence>
  </BehaviorTree>
</root>
```

## The 11 skills

| XML node | Required ports | Optional ports | Meaning |
|---|---|---|---|
| SearchFor | object | hint | Find an object and store its location |
| NavigateTo | target | — | Go to a found object, the user, or a known place |
| Say | text | emotion | Speak a short reply |
| Express | emotion | — | Show an expression |
| LookAt | target | — | Turn the head toward a target |
| Grab | object | — | Pick up a reachable small object |
| MoveArm | pose | — | Move to a named pose or target |
| Release | — | target | Release the held object, optionally at a target |
| Crush | object | — | Crush an eligible held object |
| IsVisible | object | — | Condition: object currently visible |
| IsAt | target | — | Condition: robot at target |

No invented ports: `Release object=...` and `LookAt object=...` are invalid.
Controls/decorators are listed in YAML; BT must confirm their runtime support.
Schema validity alone does not establish reachability, crushability, task
correctness, valid emotion values, or runtime safety.

## Blackboard proposal for BT review

Use literal semantic names in XML (`object="ball"`, `target="ball"`). Proposed
runtime mapping: `SearchFor("ball")` writes `ball.location`; `NavigateTo("ball")`
and `LookAt("ball")` resolve that key. `IsVisible("ball")` updates the same key
on success. `user` and named places come from BT's world state. Do not generate
unbound `{object}` / `{target}` placeholders in training examples.

These key names are proposals, not implemented ports. BT owns the final keys,
coordinate frames, freshness rules, and action success/failure behavior. Update
this contract, examples, prompts and validator together if the mapping changes.

## Decisions needed from BT / Integration

- Confirm the XML names/ports and supported controls/decorators in YAML.
- Confirm blackboard mapping, named places, arm poses and object constraints.
- Define stop/cancel handling outside tree generation. The 11 skills contain no
  Stop node; benchmark request `req_050` remains explicitly excluded, not assigned
  an invented skill. Hardware stop must not depend on successful LLM generation.
- Agree on the five emotion labels and on who turns replies into audio.

The `feature/josh/bt_functionality` main tree is an independent orchestration
sketch. It needs valid XML and runtime node registration before integration;
this contract covers generated task subtrees, not that orchestration layer.

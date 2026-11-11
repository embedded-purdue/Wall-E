---
name: generate-tree-data
description: Generate diverse, validated Wall-E (request -> behavior tree XML) fine-tuning data for the NLP tree model. Use when asked to write/augment tree training data, "generate requests from trees", or fill a person's 300-example quota.
---

# generate-tree-data

Writes `{request, tree_xml}` pairs to `training/walle/generated/<person>.json` (people: monish, akshat, adwaiy; 300 each).
A human reviews the data before anyone trains on it. Converting it to the fine-tuning format happens later, once the training notebook exists.

Python needs `pyyaml` (`pip install pyyaml`). `T=.claude/skills/generate-tree-data/gen_tools.py`

## Loop (batches of ~30)
1. `git pull` so you can see your teammates' files.
2. `python3 $T plan <person> -n 30` prints the cells to fill.
3. Fill every cell (see "Writing a cell") and append the items to `training/walle/generated/<person>.json`.
4. `python3 $T check`. Fix every problem it reports and re-run until it shows `0 problem(s)`.
5. Commit your own file. Repeat until the coverage table shows 300/300.

## Writing a cell
- **Request first.** Write what a person would actually say, in the cell's `register`, about the cell's `object`. Then write the tree that does exactly that, no more.
- Don't reuse a sentence template across cells. Vary the verb ("toss", "stick", "drop off", "bring"), the sentence shape and any added context.
- **`primary`** is the skill the request is *about*:
  - "find the apple" → `search` (just the Fallback IsVisible/SearchFor)
  - "grab the apple" → `grab` (find + go + grab)
  - Supporting steps go in the tree. The request doesn't need to mention them.
- **Archetypes** say what the tree has to contain:

| Archetype | Tree must |
|---|---|
| `*_if_visible` | Use `Fallback(Sequence(IsVisible, act), Say "I don't see ...")`, with no search |
| `grab_place_at_object` | Search for the cell's `place` and NavigateTo it, then `Release target=<place>` |
| `grab_drop_at_home` | `NavigateTo home`, then `Release target="home"` |
| `report_if_at` | Use `IsAt target="home"` or `"user"` |

- Optional cell keys:
  - `hint`: put a location in the request and pass it as `SearchFor hint="..."`.
  - `pose`, `emotion`, `message`: use them as given.
- **Item fields** (all required): `id` (= `cell`), `request`, `description`, `tree_xml`, `primary`, `archetype`, `object`, `register`, `source: "claude-generated via generate-tree-data"`, `review_status: "needs_human_review"`.
- Any whitespace in `tree_xml` is fine. `check` rewrites it to the canonical layout and stamps `split`.

## Hard rules (check enforces most of these)
- **Never train on the test set.** That's `akshat-work/model/benchmark/test_set.csv`, which is also the Google Sheet with req_001..091. It's the held-out benchmark, and `check` rejects near-copies of it.
- **Vocabulary is `akshat-work/model/wall_e.yaml` (Akshat's; matches `skills/README.md`).**
  - Only the 11 skills, with exact ports. `Release object=` and `LookAt object=` are invalid.
  - Use literal names (`object="ball"`), never `{placeholders}`.
  - Emotions and poses come from `skills/skills/mock_skills.py` (`EMOTIONS`, `NAMED_POSES`), so they always match the skills team.
  - The `crush_drop` pose only appears inside a crush.
- **Every tree must succeed on the mocks.** `check` runs it on `skills/skills/mock_skills.py` from an empty-handed start, with nothing visible:
  - Find (Fallback IsVisible/SearchFor) before you NavigateTo or LookAt an object. Only `user` and `home` need no search.
  - Grab only after NavigateTo the same object.
  - Release and Crush only while holding something.
  - Crush only empty aluminum drink cans.
- **No pure chat.** "Tell me a joke", "goodnight" and "thank you" are `conversation` in the test set and get no tree. Say is only ever part of a physical or perceptual task.
- **Nothing outside the skills.** No stop/cancel (there's no Stop node), no named rooms (kitchen, hallway), no big or unsafe objects.

## How the diversity works
- **Quotas per primary action** (`QUOTA` in gen_tools.py, 300 per person) spread data across all skills. Akshat's 14 examples and the test set are mostly find-and-go-to, with very little Crush and Release.
- **Disjoint object pools.** Each person gets every third object and every third can, so two agents never write about the same object. Within a pool, objects are used evenly.
- **Varied cells.** Each cell also varies the archetype, the register (terse, polite, slang, question, indirect, STT-style) and the hint, pose or emotion.
- **`check` rejects:**
  - near-duplicate requests (token Jaccard ≥ 0.6) against the test set, Akshat's `example_library.json` and **everyone's** files
  - any single tree shape that makes up more than 15% of the data
- **Split by family.** `split` is assigned by family (primary|archetype|object), with about 10% going to validation. Variants of a family never straddle train/validation.

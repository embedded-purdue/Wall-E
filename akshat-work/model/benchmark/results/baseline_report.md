# Wall-E NLP baseline (week 3)

_tree_results.csv: historical CSV without a provenance sidecar; runtime and exact model revisions are not recorded._

## Tree generation

Validity checks XML structure and vocabulary, not task correctness.
Tree success requires human grading. Pending means valid trees remain ungraded.

| Model | Condition | Tasks | Valid XML | Matches reference | Tree success | Ungraded | Median latency |
|---|---|---|---|---|---|---|---|
| AIRLab-POLIMI/llama-3.2-1b-it-ft-lora-bt | no_example | 49 | 34.7% (17/49) | 0.0% (0/49) | Pending (0 confirmed) | 17 | 4.78s |
| AIRLab-POLIMI/llama-3.2-1b-it-ft-lora-bt | one_example | 49 | 75.5% (37/49) | 0.0% (0/49) | Pending (0 confirmed) | 37 | 3.29s |
| meta-llama/Llama-3.2-1B-Instruct | no_example | 49 | 0.0% (0/49) | 0.0% (0/49) | 0.0% (0/49) | 0 | 14.63s |
| meta-llama/Llama-3.2-1B-Instruct | one_example | 49 | 75.5% (37/49) | 0.0% (0/49) | Pending (0 confirmed) | 37 | 2.92s |

_classifier_results.csv: historical CSV without a provenance sidecar; runtime and exact model revisions are not recorded._

## Request type (main LLM)

- Correct type: 36.3% (33/91)
- Valid JSON: 98.9% (90/91)
- Emotion matches label (where one is given): 33.3% (14/42)
- Median latency: 1.35s

| True type | Correct | Predicted as |
|---|---|---|
| task | 18.0% (9/50) | cannot_do ×35, conversation ×5, bad JSON ×1 |
| cannot_do | 100.0% (16/16) | — |
| conversation | 66.7% (8/12) | task ×4 |
| unclear | 0.0% (0/13) | cannot_do ×10, task ×2, conversation ×1 |

Misclassified:

- req_001 "Go to the ball": task → cannot_do
- req_002 "Go to the ball and grab it": task → cannot_do
- req_003 "Look at me": task → conversation
- req_004 "Wave hello": task → cannot_do
- req_005 "Come here": task → cannot_do
- req_006 "Go to the kitchen": task → cannot_do
- req_007 "Go back to your charging spot": task → cannot_do
- req_008 "Put your arm down": task → cannot_do
- req_009 "Drop it": task → cannot_do
- req_010 "Show me you're happy": task → bad JSON
- req_011 "Say hi to everyone": task → cannot_do
- req_012 "Look at the door": task → conversation
- req_013 "Find my backpack": task → cannot_do
- req_014 "Look around for my keys": task → cannot_do
- req_016 "Bring me the remote": task → cannot_do
- req_017 "Bring me my phone": task → cannot_do
- req_018 "Pick up the can and crush it": task → cannot_do
- req_019 "Crush the can I'm holding": task → cannot_do
- req_022 "Go find the ball in the other room": task → cannot_do
- req_023 "Find the can and look surprised": task → cannot_do
- req_024 "Grab the bottle, then come back to me": task → cannot_do
- req_025 "Wave goodbye and go to your charger": task → cannot_do
- req_026 "Wave at the person by the window": task → cannot_do
- req_027 "Look at the ball, then look at me": task → conversation
- req_028 "Point at the lamp": task → conversation
- req_030 "Put the cup on the table": task → cannot_do
- req_031 "Bring the ball to the box": task → cannot_do
- req_033 "Find the shoe next to the couch and bring it to the door": task → cannot_do
- req_034 "Find the bottle, crush it, and tell me when you're done": task → cannot_do
- req_037 "Find the remote and show it to me": task → cannot_do
- req_038 "If you see a can, crush it": task → cannot_do
- req_039 "Find the ball, and if you can't, tell me": task → cannot_do
- req_040 "Find the ball but don't pick it up": task → cannot_do
- req_041 "Don't move, just look at the ball": task → conversation
- req_043 "Is the ball in front of you?": task → cannot_do
- req_044 "Are you at the door yet?": task → cannot_do
- req_046 "Crush every can you find": task → cannot_do
- req_047 "Put the remote back where you found it": task → cannot_do
- req_048 "Give me a high five": task → cannot_do
- req_049 "Nod if you understand": task → cannot_do
- req_050 "Stop": task → cannot_do
- req_069 "Good job, WALL-E!": conversation → task
- req_070 "Thank you": conversation → task
- req_076 "What can you do?": conversation → task
- req_077 "Can you find things?": conversation → task
- req_078 "Get that thing": unclear → cannot_do
- req_079 "Go over there": unclear → cannot_do
- req_080 "Do the thing": unclear → cannot_do
- req_081 "Bring it here": unclear → cannot_do
- req_082 "Find it": unclear → task
- req_083 "Put that there": unclear → cannot_do
- req_084 "Go.": unclear → cannot_do
- req_085 "Crush": unclear → cannot_do
- req_086 "The ball": unclear → task
- req_087 "Can you help me?": unclear → conversation
- req_088 "Bring me something to drink": unclear → cannot_do
- req_089 "Clean up the room": unclear → cannot_do
- req_090 "Uh, go get the... never mind": unclear → cannot_do

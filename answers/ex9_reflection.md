# Ex9 — Reflection

Answer all three questions. The grader expects every question to be answered;
blank answers are zero.

---

## Q1 — Planner handoff decision

### Prompt

Find a point in your Ex7 logs where the planner decided to hand off to the
structured half. Quote the planner's reasoning or the specific subgoal's
`assigned_half` field. What signal caused the decision?

**Word count:** 100-250 words.

### Your answer

### Your answer

In the Ex7 (offline) scripted log, the loop half (executor) decided to hand off to the structured half after successfully identifying a venue. The reason provided in the tool call was: "loop half identified a candidate venue; passing to structured half for confirmation under policy rules". 
(Note: Additionally, in a live run today—`sess_77e2ab3f9af8`—the Qwen-32B executor prematurely decided to hand off with the reason "No venues found in Edinburgh for party of 4", demonstrating that the signal to hand off can also be an LLM giving up when a search yields 0 results).

### Citation (required)

- `sessions/sess_77e2ab3f9af8/logs/trace.jsonl` — `handoff_to_structured` tool call.

---

## Q2 — Dataflow integrity catch

### Prompt

Describe one instance where your Ex5 dataflow integrity check caught something
manual inspection would have missed, OR (if the check never triggered in your
runs) describe a plausible scenario where it WOULD catch a failure. Your
scenario must be specific enough that someone else could construct the test
case.

**Word count:** 100-250 words.

### Your answer

During a live `make ex5-real` run today (`sess_aaffdcbae41d`), I added hard rules to the prompt preventing the LLM from handing off to the structured half. Forced to complete the task but confused by its earlier failed venue searches, the Qwen3-32B model generated a visually perfect HTML flyer but completely hallucinated the event facts. It inserted a party size of "12" and a weather condition of "Sunny" for the date "2023-11-15". 

A human quickly reviewing the visual HTML output might have seen a properly formatted flyer and assumed the agent completed the task successfully. However, the dataflow integrity check (`fact_appears_in_log`) instantly fired and blocked the output with: `✗ dataflow FAIL: 2 unverified fact(s): ['12', 'sunny']`. It correctly recognized that those specific strings never appeared in any prior tool output (because `get_weather` was bypassed and the party size was supposed to be 6), successfully catching an LLM fabrication.

### Citation (required)

If you observed it trigger:

- `sessions/examples/ex5-edinburgh-research/sess_aaffdcbae41d/logs/trace.jsonl` — Trace shows the `generate_flyer` execution and the subsequent integrity failure.
- `sessions/examples/ex5-edinburgh-research/sess_aaffdcbae41d/workspace/flyer.html` — The HTML flyer containing the hallucinated "12" and "Sunny".

---

## Q3 — First production failure + primitive

### Prompt

If you were shipping this agent to a real pub-booking business next week,
what's the first production failure you'd expect, and which sovereign-agent
primitive (ticket state machine, manifest discipline, IPC atomic rename,
SessionQueue retry, drift-corrected scheduler, mount allowlist, HITL approval,
etc.) would surface it?

Name EXACTLY ONE primitive and EXACTLY ONE failure mode. Vague answers that
name multiple primitives or generic "something will break" failures lose
points.

**Word count:** 100-250 words.

### Your answer

**Failure Mode:** LLM Spiraling / Infinite Loops. 
When deployed to production, the most immediate failure would be the LLM repeatedly calling a search tool with varying parameters after receiving an empty response (e.g., guessing random party sizes and city areas when a specific venue is fully booked), burning through token budgets without making progress.

**Primitive:** Ticket state machine.
The ticket state machine surfaces and mitigates this failure by strictly tracking the execution state and enforcing a `max_turns` limit on the executor loop. In our live runs today (e.g., `sess_15512938026c`), when the Qwen model spiraled by calling `venue_search` 8 times with hallucinated parameters, the ticket state machine correctly caught the runaway behavior, exhausted the turn budget, and escalated the failure (`executor failed on sg_1: (max_turns=8 exhausted without final answer)`), preventing an infinite loop and saving API costs.

### Citation (optional but encouraged)

- `sessions/examples/ex5-edinburgh-research/sess_15512938026c/logs/trace.jsonl` — Trace showing the ticket state machine escalating after 8 exhausted turns.

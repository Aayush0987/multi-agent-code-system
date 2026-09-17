# Phase 0 — Study Notes

Grounding notes for the concepts this system is built on. Each section ties
the concept back to where it actually shows up in this codebase, so this
reads as applied understanding rather than abstract theory.

---

## 1. Multi-agent orchestration patterns: supervisor vs. debate/critique

**Supervisor pattern.** A central orchestrator node holds (or has access to)
the shared state and decides, after every step, which agent runs next. Agents
don't talk to each other directly or decide their own routing — the
supervisor is the single place that encodes "what happens next" logic. This
is a *macro* pattern: it's good for coordinating agents with clearly
different responsibilities (plan, write, test, review) where the sequence
and branching depend on outcomes (did the test pass? did the human approve?).

In this project: `graph/supervisor.py` — `route_after_test_gate()` is the
supervisor's entire decision function. It only looks at `test_result.passed`
and `supervisor_step` vs `supervisor_max_steps`, and returns one of two
literal branches. Everything else (how code actually gets written or
reviewed) is delegated to the subgraph it calls.

**Debate/critique loop.** Two agents take opposing roles — a proposer and a
critic — and iterate on the *same artifact* until the critic is satisfied or
a round limit is hit. Unlike the supervisor pattern, there's no need for
branching logic beyond "approve or send back"; the loop is a tight,
bounded cycle between exactly two roles. This is a *micro* pattern: it's good
for quality refinement on a single artifact (here, code), where a second
perspective catches things the first pass missed.

In this project: `graph/critique_loop.py` — Coder and Reviewer are the
proposer/critic pair, `route_after_review()` is the only branch, and the
loop is capped by `critique_max_rounds` independently of anything at the
supervisor level.

**Why compose them.** They solve different problems and compose cleanly
because the critique loop is just *one node* from the supervisor's point of
view (`critique_loop_node` in `supervisor.py` invokes the compiled critique
loop graph and returns a flat dict). The supervisor doesn't need to know
that node internally loops — it only sees the final result and its own
routing question ("did the final output pass?"). This mirrors how production
multi-agent systems are often layered: coarse-grained routing at the top,
fine-grained iterative refinement inside individual steps.

## 2. LangGraph fundamentals

- **StateGraph**: a graph whose nodes are functions `state -> partial_state`,
  and whose shared state is a typed dict (here, `AgentState` in
  `graph/state.py`). Every node receives the *full current state* and
  returns a dict of the keys it wants to update; LangGraph merges the
  returned dict into state before the next node runs.
- **Nodes**: plain Python callables. No special base class — `coder_node`,
  `reviewer_node`, `planner_node`, etc. are just functions registered with
  `graph.add_node(name, fn)`.
- **Edges**: fixed transitions (`graph.add_edge(a, b)`) vs. **conditional
  edges** (`graph.add_conditional_edges(node, router_fn, {label: target})`),
  where `router_fn(state) -> label` decides the next node dynamically. Both
  loops in this project (critique loop, supervisor loop) are implemented as
  a conditional edge that either loops back to an earlier node or proceeds
  to `END`.
- **Compilation**: `graph.compile()` turns the builder into an invokable
  graph (`.invoke(state, config=...)`). The `recursion_limit` in `config` is
  the safety ceiling on total node executions — important here because both
  loops are cyclic graphs, and a bug in the routing function could otherwise
  spin forever.
- **Checkpointing**: LangGraph can persist state between invocations (e.g. to
  resume after an `interrupt()`). Not yet wired in this project — needed in
  Phase 5 so the graph can pause at the human checkpoint and resume with the
  human's decision rather than losing all state.

## 3. Human-in-the-loop interrupt patterns

LangGraph's `interrupt()` (from `langgraph.types`) pauses graph execution
inside a node and surfaces a payload to the calling code, without ending the
run. The graph's execution state is frozen; resuming requires invoking the
graph again with a special `Command(resume=...)` value and the *same thread
ID*, which needs a checkpointer (e.g. `MemorySaver` for local/in-process use)
so the framework knows where to pick back up.

This differs from just returning from the graph and calling it again with
new input: `interrupt()` preserves everything in-flight (the full state
accumulated so far — code, test results, critique history) so the resumed
run doesn't need to reconstruct any of it.

For this project (Phase 5), the plan is:
- Add a `MemorySaver` checkpointer when compiling the supervisor graph
- Replace `human_checkpoint_node`'s stub with an `interrupt()` call that
  emits the final code, test results, reviewer verdict, and critique history
- The calling code (CLI) catches the interrupt, prompts the human, and
  resumes the graph with `Command(resume={"decision": "approve"/"reject", "feedback": ...})`
- On reject, the resumed graph routes back into the critique loop with the
  human's feedback folded into `review_feedback`

## 4. Agent memory / state management across turns

"Memory" here just means: what's visible to each node when it runs. Because
every node reads the *entire* shared `AgentState`, there's no separate
memory subsystem — state IS the memory. Two things matter:

- **What accumulates vs. what gets overwritten.** Fields like `code`,
  `test_result`, `review_verdict` are overwritten each round (only the
  latest matters). Fields like `critique_history` and `trace` are
  explicitly accumulated (read the existing list, append, return the new
  list) — LangGraph's default merge behavior is "replace the key", not
  "append to the list", so accumulation has to be done manually inside the
  node (see `reviewer_node` in `critique_loop.py`).
- **Scoping between the two loops.** The critique loop gets a *fresh* substate
  on each supervisor retry (`critique_round` reset to 0 in
  `critique_loop_node`) — the supervisor's memory of *how many times it has
  retried* is separate from the critique loop's memory of *how many rounds
  this attempt has used*. Conflating the two would make the bounds
  meaningless (e.g. a supervisor retry would start already near the critique
  loop's cap).

## 5. Agent trajectory evaluation

Evaluating a multi-agent system on the final output alone hides most of what
actually matters for debugging and trust: which agent ran, in what order,
how many loop iterations were spent, and where a run diverged from the
happy path. This project's `trace` list (accumulated across both graphs) is
exactly this: each entry records which agent/decision fired and the
relevant outcome (e.g. `{"agent": "supervisor", "decision": "critique_loop",
"critique_rounds_used": 2, "critique_outcome": "approve"}`).

Trajectory evaluation questions this enables, planned for Phase 7/8:
- Did the system take the *efficient* path (1 round, 1 step) or grind
  through retries?
- When it failed, which agent's output caused the failure — was the Coder
  wrong, or did the Reviewer approve something it shouldn't have?
- Are loop bounds being hit often (signal that prompts/models need tuning)
  or never (signal that bounds could be tighter without losing quality)?

This is distinct from output evaluation (is the final code correct) and is
the more useful lens for improving the *system*, not just a single run.

## 6. Safe code execution practices

Running LLM-generated code always carries risk (the code might have bugs,
resource-exhausting loops, or, if the model is adversarially prompted,
deliberately harmful behavior). The brief scopes this project to **local
subprocess-based execution, no cloud** — meaning we accept a lighter security
posture than a real sandbox (container, VM, gVisor, etc.) in exchange for
simplicity, since this runs entirely on the user's own machine on
Groq/Gemini/Ollama-generated code the user themselves requested.

What `sandbox/executor.py` actually does:
- **Isolated temp directory** — code never touches the project directory
- **Hard wall-clock timeout** (`subprocess.run(..., timeout=...)`) — kills
  infinite loops or hangs; verified in `tests/test_tester.py`
- **Stripped environment** — the subprocess gets a minimal `PATH` only, not
  the parent's full environment (so it can't read `GROQ_API_KEY` etc. from
  the environment even by accident)
- **Best-effort POSIX rlimits** (`RLIMIT_CPU`, `RLIMIT_AS`) — caps runaway
  CPU/memory use, applied via `preexec_fn`

What it does **not** do (explicitly out of scope, to be called out in the
README's Limitations section): no network namespace isolation, no seccomp/
syscall filtering, no filesystem access control beyond cwd. A determined
malicious payload (rather than an ordinary buggy LLM completion) could still
do things like make network calls. This is an acceptable tradeoff for a
local, single-user dev tool — it would not be acceptable for running
untrusted third-party code in a shared or production environment.

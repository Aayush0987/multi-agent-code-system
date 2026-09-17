# Build Brief: Multi-Agent Code Generation & Review System

## Project Summary
A multi-agent system that plans, writes, tests, and reviews code for a given task,
using a **supervisor orchestration pattern** for overall task routing, with a
**debate/critique loop** embedded between the Coder and Reviewer agents for
iterative refinement. Includes a human-in-the-loop approval checkpoint before
final delivery.

## Orchestration Design (two patterns, composed)
- **Supervisor pattern (outer loop)**: a central orchestrator node examines
  current state after each agent's turn and decides which agent acts next
  (Planner → Coder → Tester → Reviewer → human checkpoint), based on task
  progress and results.
- **Debate/critique loop (inner loop, nested)**: the Coder and Reviewer form a
  proposer/critic pair. The Coder produces code; the Reviewer critiques it
  (correctness, quality, test results); the Coder revises based on that
  critique. This repeats for a bounded number of rounds, or until the Reviewer
  approves — this is the same principle as classic debate/critique multi-agent
  patterns (iterative refinement through critique, shown to catch errors a
  single generation pass misses), just operating on a bounded loop within the
  broader supervisor architecture rather than as the system's only structure.

This composition — supervisor for macro task routing, critique loop for
micro-level quality refinement — reflects how many production multi-agent
systems are actually structured, and is worth calling out explicitly in the
README as a deliberate architectural choice.

## Agents
- **Supervisor** — orchestrator; decides next agent based on state
- **Planner** — breaks the task into steps/subtasks
- **Coder** — writes/edits code based on the plan (and Reviewer feedback, in
  the critique loop)
- **Tester** — actually executes the code, reports pass/fail and errors
- **Reviewer** — critiques code quality/correctness and test results; either
  approves or sends back to Coder with specific feedback (the critic role in
  the debate/critique loop)

## Human-in-the-Loop
Before final delivery, the system pauses and presents: final code, test
results, Reviewer's verdict. The human can approve (end) or reject with
feedback (loop back to Coder, with human feedback added to state).

## Tech Stack
- **Orchestration**: LangGraph (StateGraph, conditional edges, interrupts for
  human-in-the-loop)
- **LLM(s)**: to be decided per agent role at build time — free/local or
  free-tier, consistent with prior projects' cost constraint
- **Code execution**: local subprocess-based sandboxed execution (no cloud)
- **Interface**: CLI or lightweight UI for the human-approval step

---

## Phase 0 — Study
- Multi-agent orchestration patterns: supervisor pattern, debate/critique loop,
  and how they compose (this project uses both)
- LangGraph fundamentals: StateGraph, nodes, edges, conditional edges, checkpointing
- Human-in-the-loop interrupt patterns in LangGraph
- Agent memory/state management across turns
- Agent trajectory evaluation — judging the process (which agent, how many
  loops, where time was spent), not just the final output
- Safe code execution practices (sandboxing considerations for local execution)

## Phase 1 — Define Shared State Schema
- Task spec, current plan, current code, test results, review feedback,
  critique-loop iteration count, human feedback (if any)
- This shared state is what every LangGraph node reads/writes

## Phase 2 — Build Individual Agents (standalone first)
- **Planner**: task description → structured step-by-step plan
- **Coder**: plan (+ any prior Reviewer/human feedback) → code
- **Tester**: executes the code, captures pass/fail + error output
- **Reviewer**: code + test results → verdict (approve / send back with
  specific, actionable feedback)
- Test each agent independently with fixed inputs before wiring them together

## Phase 3 — Debate/Critique Loop (Coder ↔ Reviewer)
- Implement the bounded inner loop: Coder produces code → Reviewer critiques →
  Coder revises based on critique → Reviewer re-checks
- Set a max iteration count for this inner loop specifically (separate from
  the outer supervisor's overall iteration limit) to prevent unbounded
  back-and-forth
- Log each round: what the Reviewer flagged, what the Coder changed in response

## Phase 4 — Supervisor Logic (outer loop)
- Build the orchestrator node: given current state, decide the next macro step
  (Planner → Coder/Reviewer critique loop → Tester → human checkpoint, with
  routing back to the critique loop if Tester fails)
- Implement as LangGraph conditional edges driven by state (test pass/fail,
  critique loop outcome, human decision)

## Phase 5 — Human-in-the-Loop Checkpoint
- LangGraph interrupt before final delivery
- Present: final code, test results, Reviewer's verdict, critique-loop history
- Two outcomes: approve (end) or reject with feedback (loop back into the
  Coder/Reviewer critique loop, human feedback added to state)

## Phase 6 — Loop Control & Safety
- Max iteration limits on both the inner critique loop and the outer
  supervisor loop
- Log every iteration at both levels with what changed and why

## Phase 7 — Observability / Tracing
- Log each agent's input/output, timestamps, and supervisor decisions
- Build a simple trace view (structured log or minimal UI) showing the full
  path: macro steps taken, critique-loop rounds within each, where time was spent
- Optional: note the conceptual link to the eval/observability project — this
  is the kind of trace data such a tool would consume

## Phase 8 — End-to-End Testing
- Run the full pipeline on varied coding tasks (different difficulty levels)
- Include at least one case where the Tester fails and the system correctly
  routes back into the critique loop
- Include at least one case demonstrating multiple critique-loop rounds before
  Reviewer approval
- Include the human-rejection path at least once, verifying correct re-loop

## Phase 9 — Documentation
README should include:
- Architecture diagram showing both the outer supervisor flow and the nested
  Coder↔Reviewer critique loop
- Explicit explanation of why both patterns were used and how they compose
- Example run traces: a clean success case, a critique-loop case (multiple
  rounds), and a human-rejection case
- Iteration/timing stats across test tasks (outer loop count, inner critique
  loop count per task)
- Limitations (sandboxing depth, model choice tradeoffs, loop bound choices)
- Lessons learned

---

## Success Criteria
- All four agents work correctly in isolation and in the full pipeline
- Debate/critique loop correctly refines code across multiple rounds when needed
- Supervisor correctly routes at the macro level, including loop-back on test failure
- Human-in-the-loop checkpoint functions correctly for both approve and reject paths
- Clear trace/log showing the full decision path — both outer and inner loops — for any given run
- Documented, reproducible, interview-ready README

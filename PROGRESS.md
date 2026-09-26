# Progress Tracker — Multi-Agent Code Generation & Review System

Tracks status against `build-brief-multi-agent-code-system.md`. Update the
checkbox when a phase's work is done and verified, not just started.
Pushed to GitHub in stages at the user's direction; the full repo was pushed
after Phase 9.

## Setup
- [x] Project scaffold created (`agents/`, `graph/`, `sandbox/`, `cli/`, `tests/`, `logs/`, `docs/`)
- [x] `uv` project initialized (`pyproject.toml`)
- [x] Core deps added: langgraph, langchain-core, langchain-groq, langchain-google-genai, langchain-ollama, python-dotenv, rich
- [x] Pluggable LLM backend (`agents/llm.py`) — supports Groq / Gemini / Ollama, selectable via env var, overridable per agent role
- [x] Shared state schema drafted (`graph/state.py`)
- [x] `.env` configured with Groq API key; connectivity verified (`openai/gpt-oss-120b`)

## Phase 0 — Study
- [x] Supervisor pattern & debate/critique loop, and how they compose
- [x] LangGraph fundamentals: StateGraph, nodes, edges, conditional edges, checkpointing
- [x] Human-in-the-loop interrupt patterns in LangGraph
- [x] Agent memory/state management across turns
- [x] Agent trajectory evaluation concepts
- [x] Safe local code execution / sandboxing considerations
- Written up in `docs/phase0-study-notes.md`, grounded against the actual code in Phases 1-4

## Phase 1 — Shared State Schema
- [x] Draft schema (task, plan, code, test results, review feedback, critique-loop count, human feedback)
- [ ] Reviewed/finalized once agents are wired together

## Phase 2 — Individual Agents (standalone)
- [x] Planner: task → structured plan (`agents/planner.py`)
- [x] Coder: plan (+ feedback) → code (`agents/coder.py`, extracts fenced ```python block)
- [x] Tester: executes code, captures pass/fail + errors (`agents/tester.py` + `sandbox/executor.py`)
- [x] Reviewer: code + test results → verdict + feedback (`agents/reviewer.py`, JSON verdict)
- [x] Each agent tested independently with fixed inputs — `uv run pytest tests/` — 8/8 passing
  - Planner produces a numbered plan
  - Coder produces runnable code with `is_palindrome`, and revises on feedback
  - Tester correctly passes/fails/times-out (good code, bad code, infinite loop)
  - Reviewer approves passing code, sends back failing code with feedback

## Phase 3 — Debate/Critique Loop (Coder ↔ Reviewer)
- [x] Bounded inner loop implemented as a LangGraph subgraph (`graph/critique_loop.py`): Coder → Tester → Reviewer → conditional (revise back to Coder / done)
- [x] Max iteration count enforced independently (`critique_max_rounds`, checked in `route_after_review`, separate from the outer supervisor's own limit)
- [x] Per-round logging — `critique_history` records round number, code snapshot, reviewer feedback, verdict; also appended to `trace`
- [x] Tested: `uv run pytest tests/test_critique_loop.py` — 4/4 passing
  - Immediate approval stops loop at round 1
  - Revise → approve stops at round 2, history captures both rounds' feedback
  - Loop is bounded — 3x "revise" verdicts still halts at max_rounds=3, doesn't spin forever
  - Live end-to-end run against real Groq agents terminates correctly (approved on round 1 for the test task; a forced multi-round case is planned for Phase 8 with a harder task)

## Phase 4 — Supervisor Logic (outer loop)
- [x] Orchestrator graph built (`graph/supervisor.py`): Planner → critique loop → test gate → human checkpoint
- [x] Conditional edges driven by state (`route_after_test_gate`): passed → human checkpoint; failed + steps remain → retry; failed + steps exhausted → human checkpoint anyway (bounded, best-effort delivery)
- [x] Loop-back to a *fresh* critique-loop attempt on test failure — `supervisor_step` and inner `critique_max_rounds` are independent bounds
- [x] `human_checkpoint` node — see Phase 5, now a real `interrupt()` (built same session as Phase 4's stub, upgraded immediately after)
- Superseded by Phase 5's supervisor test suite (below)

## Phase 5 — Human-in-the-Loop Checkpoint
- [x] Real LangGraph `interrupt()` before final delivery (`graph/supervisor.py::human_checkpoint_node`), backed by `MemorySaver` checkpointer + thread-id session (`SupervisorSession`)
- [x] Presents final code, test results, reviewer verdict, critique-loop history, supervisor step count — via the interrupt payload, rendered in `cli/main.py` with `rich`
- [x] Two outcomes: approve → end; reject + feedback → loops back into a *fresh* critique-loop attempt, human feedback folded into `review_feedback` for the Coder's next revision
- [x] Reject is still bounded by `supervisor_max_steps` — a human can't force retries past the configured limit; forced to end (best-effort delivery) once exhausted
- [x] Interactive CLI (`cli/main.py`) — `uv run python -m cli.main "<task>"` — drives the full approve/reject loop with a human at the keyboard; smoke-tested end-to-end
- [x] Tested: `uv run pytest tests/test_supervisor.py` — 5/5 passing
  - Pauses correctly at first pass, approve ends cleanly
  - Retries automatically on test failure (no human involved) then succeeds
  - Bounded: max-steps-exhausted + human reject still forces a clean end, not an infinite loop
  - Reject-then-approve: human rejection on passing tests loops back into a fresh critique-loop attempt, second attempt then approved
  - Live end-to-end run against real Groq agents, through a real pause/resume
- Full suite: `uv run pytest tests/` — 17/17 passing (one flaked once on Groq free-tier rate limiting — 8000 TPM — not a code issue; passed on retry. Note for Phase 8: pace live test runs to avoid this.)

## Phase 6 — Loop Control & Safety
- [x] Max iteration limits (inner `critique_max_rounds`, outer `supervisor_max_steps`) — implemented in Phases 3/4, independently enforced, verified bounded even under worst-case (always-revise / always-reject) in tests
- [x] Full iteration logging at both levels with what changed and why (`graph/trace.py::log_event` + `diff_summary`)
  - Coder: logs a truncated unified diff vs. the previous round's code, plus the feedback ("reason") that triggered the revision
  - Tester: logs pass/fail, exit code, stderr excerpt per round
  - Reviewer: logs verdict + feedback ("reason") per round
  - Supervisor: logs planner/critique_loop/test_gate/human_checkpoint decisions, each with a "reason" (e.g. why a retry was triggered, what the human said)
- [x] Tested: `uv run pytest tests/` — 15/17 passing on Groq before quota exhaustion; switched `LLM_PROVIDER` to Gemini (see Decisions Log) and re-ran — 17/17 passing.

## Phase 7 — Observability / Tracing
- [x] Per-agent input/output + timestamp logging — already flowing from Phase 6's `log_event`; full code per round preserved in `critique_history`
- [x] Supervisor decision logging — already flowing from Phase 6
- [x] Run persistence: `graph/observability.py::save_run_log` writes each run's full trace + outcome to `logs/<run_id>.json`, wired into `cli/main.py` (auto-saves after every run)
- [x] Simple trace view: `cli/trace_view.py` — `uv run python -m cli.trace_view [log_path]` (defaults to most recent run)
  - `walk_trace()` regroups the flat trace back into macro steps (Planner / each critique-loop attempt / test gate / human checkpoint), each showing its nested per-round Coder/Tester/Reviewer entries
  - `compute_timing()` shows total time spent per agent — confirms LLM calls (Coder/Reviewer) dominate wall-clock time vs. Tester/supervisor overhead
  - Smoke-tested live: ran a full CLI session (Fibonacci task), viewed the resulting trace — correctly showed 1 supervisor step, 1 critique round, and a timing table
- [x] Tested: `uv run pytest tests/test_observability.py` — 3/3 passing (deterministic, synthetic trace — walk grouping, timing math, JSON save/load roundtrip)
- Full suite: `uv run pytest tests/` — 20/20 passing

## Phase 8 — End-to-End Testing
- [x] Varied task difficulty runs (`tests/test_e2e.py`), all against the real pipeline (real Planner/Coder/Reviewer via Gemini, real Tester execution):
  - Easy: `is_even` — approved round 1, step 1
  - Medium: `merge_intervals` — approved round 1, step 1
  - Hard: `next_greater_circular` (circular next-greater-element) — approved round 1, step 1 (this model got it right first try; documented honestly rather than forced)
- [x] Case: multiple critique-loop rounds before approval — `test_e2e_multi_round_critique_with_real_agents`. Real Coder + real Reviewer throughout; the Tester's *first* result is fault-injected to fail (real Tester for all subsequent calls) so the revise→fix→approve path is reliably exercised rather than hoping a real model errs on try 1. Result: 2 rounds, history `['revise', 'approve']`.
- [x] Case: Tester fails → supervisor correctly routes back into a fresh critique-loop attempt — `test_e2e_supervisor_retries_on_forced_test_failure`. Same fault-injection technique, `critique_max_rounds=1` so the critique loop can't self-heal within one attempt, forcing the *supervisor's own* retry routing to fire. Result: 2 supervisor steps, final test passed.
- [x] Case: human-rejection path → correct re-loop — `test_e2e_human_rejection_loops_back_and_incorporates_feedback`. Live run, human rejects passing-tests code with real feedback ("add a docstring"), verified the next attempt's code actually contains the requested docstring, then approved.
- All 6 Phase 8 tests + full suite passing: `uv run pytest tests/` — **26/26 passing** (67s for just e2e, ~3 min for the full suite)

## Phase 9 — Documentation
- [x] Architecture diagram (mermaid, outer supervisor + nested critique loop) — README.md
- [x] Explanation of why both patterns are used and how they compose — README.md
- [x] Example run traces (clean success, multi-round critique, human-rejection) — README.md + `docs/traces/`, generated by `scripts/generate_examples.py` from real runs
- [x] Iteration/timing stats across tasks — README.md table + `docs/traces/stats.json`
- [x] Limitations section (incl. Reviewer not seeing task/plan, Coder-written tests, sandbox depth, live-test flakiness)
- [x] Lessons learned
- Final full run: 24/26 passing; the 2 live e2e failures passed on immediate rerun (LLM non-determinism, noted in README).

## After Phase 9 — fixes and web UI
- [x] Coder now receives its previous code on revisions (`agents/coder.py`, carried across supervisor retries in `graph/supervisor.py`)
- [x] Human checkpoint reports `steps_remaining`, accepts `extra_steps` on reject, and flags `rejection_unapplied`; CLI warns and offers extra steps
- [x] Web UI: `api/` (FastAPI, background-thread sessions, access code, concurrency cap) + `web/` (static, no build). Live event streaming via a context-var listener in `graph/trace.py`
- [x] Verified: 31 deterministic tests pass (8 of them API tests with mocked agents); real run through the HTTP API; real Chrome run via `scripts/ui_smoke.py` (run -> reject with feedback -> approve -> download), no console errors
- [x] Dockerfile built and deployed via Render (free plan)
- [x] Deployed: frontend on Vercel (https://multi-agent-code-system.vercel.app), backend on Render (https://multi-agent-code-api.onrender.com). CORS_ORIGINS set to both the production Vercel domain and the initial preview deployment URL. Verified live: ran the LRU cache task through the deployed pipeline end-to-end (Planner → Coder → Tester passed → Reviewer approved → human checkpoint).

## Git / GitHub
- [x] Local git init
- [x] Commits pushed in stages (scaffold, Phases 0-1, 2-3, 4-5), then Phases 7-9 together
- [x] Pushed to https://github.com/Aayush0987/multi-agent-code-system

## Decisions Log
- LLM backend: pluggable (Groq / Gemini / Ollama), chosen via `LLM_PROVIDER` env var, overridable per agent role. User has a Groq key, can get a Gemini key, and may install a local model via Ollama.
- Default Groq model: `openai/gpt-oss-120b` (llama-3.3-70b-versatile is no longer available on this key's model list; gpt-oss-120b confirmed working).
- Switched active provider to Gemini (`LLM_PROVIDER=gemini`) after Groq's free-tier daily quota (200,000 TPD) was exhausted mid-Phase-6. Default Gemini model: `gemini-flash-lite-latest` (gemini-2.0-flash, gemini-2.5-flash, and gemini-2.5-flash-lite are all "no longer available to new users" on this key; gemini-3.6-flash exists but its free tier is only 20 requests/day, too tight for this workload; gemini-flash-lite-latest works and is noticeably faster than Groq in practice). Groq key is still in `.env` and the backend is pluggable — can switch back anytime via `LLM_PROVIDER=groq`.
- Bug found + fixed while switching: some Gemini models return `AIMessage.content` as a list of structured content blocks rather than a plain string, which broke the agents' regex/JSON parsing (`agents/coder.py`, `agents/reviewer.py` assumed `str`). Fixed by adding `agents/llm.py::extract_text()` / `invoke_text()` — a provider-agnostic normalizer all three LLM-calling agents now use instead of touching `response.content` directly.
- Env/dependency manager: `uv`.
- No git tracking until explicitly requested.

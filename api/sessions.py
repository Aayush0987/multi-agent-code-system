"""In-memory run sessions for the web API.

Each session runs the supervisor graph on a background thread, records every
trace event as it happens, and parks at the human checkpoint until a decision
arrives. State lives in this process's memory (matching the `MemorySaver`
checkpointer), so the API must run as a single long-lived process.
"""
from __future__ import annotations

import threading
import time
import uuid

from graph.observability import save_run_log
from graph.supervisor import SupervisorSession
from graph.trace import set_event_listener

FINISHED_SESSION_TTL_SECONDS = 3600


class RunSession:
    def __init__(self, task: str, critique_max_rounds: int, supervisor_max_steps: int):
        self.id = uuid.uuid4().hex[:12]
        self.task = task
        self.created = time.time()
        self.status = "running"  # running | awaiting_human | done | error
        self.events: list[dict] = []
        self.checkpoint: dict | None = None
        self.result: dict | None = None
        self.error: str | None = None
        self._lock = threading.Lock()
        self._supervisor = SupervisorSession(
            critique_max_rounds=critique_max_rounds,
            supervisor_max_steps=supervisor_max_steps,
        )

    # -- events ---------------------------------------------------------
    def _emit(self, event: dict) -> None:
        with self._lock:
            self.events.append({"seq": len(self.events), **event})

    def _note(self, label: str) -> None:
        self._emit({"timestamp": time.time(), "agent": "system", "event": label})

    # -- running the graph on a worker thread --------------------------
    def _run(self, action) -> None:
        set_event_listener(self._emit)
        try:
            state = action()
            with self._lock:
                if SupervisorSession.is_paused(state):
                    self.checkpoint = SupervisorSession.interrupt_payload(state)
                    self.status = "awaiting_human"
                else:
                    self.result = {
                        "code": state.get("code"),
                        "human_decision": state.get("human_decision"),
                        "supervisor_steps": state.get("supervisor_step"),
                        "test_passed": (state.get("test_result") or {}).get("passed"),
                        "rejection_unapplied": bool(state.get("rejection_unapplied")),
                    }
                    self.status = "done"
            if self.status == "done":
                save_run_log(self.id, state, self.task)
        except Exception as exc:  # surfaced to the UI instead of dying silently
            with self._lock:
                self.error = f"{type(exc).__name__}: {exc}"
                self.status = "error"
        finally:
            set_event_listener(None)

    def _spawn(self, action) -> None:
        threading.Thread(target=self._run, args=(action,), daemon=True).start()

    def start(self) -> None:
        self._note("started")
        self._spawn(lambda: self._supervisor.start(self.task))

    def decide(self, decision: str, feedback: str | None, extra_steps: int) -> None:
        with self._lock:
            if self.status != "awaiting_human":
                raise ValueError("session is not waiting for a decision")
            self.status = "running"
            self.checkpoint = None
        self._note(f"human {decision}d" if decision == "approve" else "human rejected")
        self._spawn(lambda: self._supervisor.resume(decision, feedback, extra_steps))

    # -- reading --------------------------------------------------------
    def snapshot(self, since: int) -> dict:
        with self._lock:
            return {
                "id": self.id,
                "task": self.task,
                "status": self.status,
                "events": self.events[since:],
                "next": len(self.events),
                "checkpoint": self.checkpoint,
                "result": self.result,
                "error": self.error,
            }


class SessionStore:
    def __init__(self, max_active: int):
        self.max_active = max_active
        self._sessions: dict[str, RunSession] = {}
        self._lock = threading.Lock()

    def _evict_old(self) -> None:
        now = time.time()
        for sid in [
            sid for sid, s in self._sessions.items()
            if s.status in ("done", "error") and now - s.created > FINISHED_SESSION_TTL_SECONDS
        ]:
            del self._sessions[sid]

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.status in ("running", "awaiting_human"))

    def create(self, task: str, critique_max_rounds: int, supervisor_max_steps: int) -> RunSession:
        with self._lock:
            self._evict_old()
            if self.active_count() >= self.max_active:
                raise RuntimeError("too many active sessions, try again shortly")
            session = RunSession(task, critique_max_rounds, supervisor_max_steps)
            self._sessions[session.id] = session
        session.start()
        return session

    def get(self, session_id: str) -> RunSession | None:
        return self._sessions.get(session_id)

"""Deterministic patient-advocacy simulator.

Given an agent tool call, return the party's reply from world state, append to an
append-only event log, and never invent facts: every reply string comes from the
world file. Runs are capped at MAX_STEPS tool calls.
"""
from __future__ import annotations

import copy

MAX_STEPS = 60
TOOLS = ("contact_party", "share_info", "fill_form", "read_document", "wait", "note")
UNKNOWN_REPLY = "I don't have information on that."


class Sim:
    def __init__(self, world: dict, max_steps: int = MAX_STEPS):
        self.world = world
        self.max_steps = max_steps
        self.flags = {k for k, v in world["initial_flags"].items() if v}
        self.step = 0
        self.events: list[dict] = []
        self.fired: set[str] = set()
        self.ended = False
        self._append({
            "tool": "run_start", "party": None, "topic": None, "action_id": None, "result": "ok",
            "requires": [], "sets": [], "reveals": [], "disclosed": [], "reply": "Run started.",
            "initial_flags": sorted(self.flags),
        })

    # ------------------------------------------------------------------ log
    def _append(self, ev: dict) -> dict:
        ev = {"id": f"e{len(self.events) + 1:03d}", "step": self.step, **ev}
        self.events.append(ev)
        return ev

    # ----------------------------------------------------------------- state
    def unmet_outcomes(self) -> list[str]:
        return [o for o in self.world["required_outcomes"] if o not in self.flags]

    def finish(self, reason: str = "agent_done") -> dict:
        """Append the terminal event (idempotent). Records which outcomes are unmet."""
        if self.ended:
            return self.events[-1]
        self.ended = True
        return self._append({
            "tool": "run_end", "party": None, "topic": None, "action_id": None, "result": "ok",
            "requires": [], "sets": [], "reveals": [], "disclosed": [], "reason": reason,
            "reply": "Run ended.", "unmet_outcomes": self.unmet_outcomes(), "final_flags": sorted(self.flags),
        })

    # ------------------------------------------------------------------ tools
    def call(self, tool: str, party: str | None = None, topic: str | None = None, **args) -> dict:
        """Execute one tool call. Returns {event_id, result, reply}."""
        if self.ended:
            return {"event_id": None, "result": "rejected", "reply": "The run has ended."}
        if self.step >= self.max_steps:
            self.finish("step_limit")
            return {"event_id": self.events[-1]["id"], "result": "rejected", "reply": "Step limit reached."}
        self.step += 1
        base = {"tool": tool, "party": party, "topic": topic, "action_id": None, "requires": [],
                "sets": [], "reveals": [], "disclosed": [], "args": {k: v for k, v in args.items()}}

        if tool not in TOOLS:
            return self._done(base, "invalid", f"Unknown tool '{tool}'.")
        if tool in ("contact_party", "share_info", "fill_form") and party not in self.world["parties"]:
            return self._done(base, "invalid", f"Unknown party '{party}'.")
        if tool == "note":
            return self._done(base, "ok", "Noted.")
        if tool == "wait":
            return self._wait(base)

        action = self._match(tool, party, topic)
        if action is None:
            if tool == "share_info" and topic in self.world["protected_info"]:
                base["disclosed"] = [{"info": topic, "to": party}]
                return self._done(base, "ok", f"{self._name(party)} received the information.")
            return self._done(base, "unknown", UNKNOWN_REPLY)
        return self._apply(base, action)

    def _name(self, party):
        return self.world["parties"][party]["name"]

    def _match(self, tool, party, topic):
        for a in self.world["actions"]:
            if a["tool"] != tool or a["topic"] != topic:
                continue
            if tool == "read_document" or a.get("party") == party:
                return a
        return None

    def _wait(self, base):
        for a in self.world["actions"]:
            if a["tool"] == "wait" and a["id"] not in self.fired and all(r in self.flags for r in a["requires"]):
                return self._apply(base, a)
        return self._done(base, "noop", "Time passes. Nothing new has arrived.")

    def _apply(self, base, a):
        base["action_id"] = a["id"]
        base["requires"] = list(a["requires"])
        base["prohibited"] = bool(a.get("prohibited"))
        if a["id"] in self.fired:
            return self._done(base, "noop", "That has already been done.")
        missing = [r for r in a["requires"] if r not in self.flags]
        if missing:
            labels = [self.world["flags"].get(m, m) for m in missing]
            return self._done(base, "blocked", "I can't proceed yet. Still needed: " + "; ".join(labels) + ".")
        self.fired.add(a["id"])
        new = [s for s in a["sets"] if s not in self.flags]
        self.flags.update(a["sets"])
        base["sets"] = new
        base["reveals"] = list(a.get("reveals", []))
        if a["tool"] in ("share_info", "fill_form") or a.get("discloses"):
            base["disclosed"] = [{"info": i, "to": a.get("party")} for i in a.get("discloses", [])]
            if a["tool"] == "share_info" and a["topic"] in self.world["protected_info"] and not base["disclosed"]:
                base["disclosed"] = [{"info": a["topic"], "to": a["party"]}]
        return self._done(base, "ok", a["reply"])

    def _done(self, base, result, reply):
        ev = self._append({**base, "result": result, "reply": reply})
        return {"event_id": ev["id"], "result": result, "reply": reply}

    # --------------------------------------------------------------- helpers
    def snapshot(self) -> dict:
        return copy.deepcopy({"flags": sorted(self.flags), "step": self.step, "events": self.events})

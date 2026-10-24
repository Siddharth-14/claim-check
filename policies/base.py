"""Shared builder for the four scripted policies.

Every policy executes (part of) the reachability plan through the simulator, narrating each step in the first person,
then writes a final message. Messages carry `gold_claims` (the structured claims the sentence encodes) used only by
tests; the production pipeline re-extracts claims from the text with the local model.
"""
from __future__ import annotations

from sim.engine import Sim
from sim.reachability import plan


def action(world, aid):
    return next(a for a in world["actions"] if a["id"] == aid)


def call_for(a):
    kw = {"party": a.get("party"), "topic": a.get("topic")}
    return a["tool"], kw


def fmt_call(tool, kw):
    parts = [f"{k}={v}" for k, v in kw.items() if v is not None]
    return f"{tool}({', '.join(parts)})"


class Recorder:
    def __init__(self, world, policy):
        self.world, self.policy = world, policy
        self.sim = Sim(world)
        self.transcript = [{"speaker": "user", "text": world["brief"]}]

    def say(self, text, gold=()):
        self.transcript.append({"speaker": "agent", "text": text, "gold_claims": list(gold)})

    def do(self, tool, narrate=None, gold_action=None, **kw):
        r = self.sim.call(tool, **kw)
        self.transcript.append({"speaker": "tool", "text": fmt_call(tool, kw), "event_id": r["event_id"]})
        p = kw.get("party")
        self.transcript.append({"speaker": "party", "party": p, "text": r["reply"], "event_id": r["event_id"]})
        if narrate:
            self.say(narrate, [{"kind": "action", "entity": gold_action, "asserted_state": "performed"}] if gold_action else [])
        return r

    def run_action(self, aid, narrate=True):
        a = action(self.world, aid)
        tool, kw = call_for(a)
        return self.do(tool, narrate=a["narration"] if narrate else None, gold_action=aid, **kw)

    def final_message(self, extra_sentences=(), extra_gold=()):
        labels = [self.world["flags"][o] for o in self.world["required_outcomes"]]
        text = " ".join(list(extra_sentences)) + (" " if extra_sentences else "") + \
            "Final status: " + "; ".join(labels) + "."
        gold = list(extra_gold) + [{"kind": "outcome", "entity": o, "asserted_state": "true"} for o in self.world["required_outcomes"]]
        self.say(text, gold)

    def finish(self):
        self.sim.finish("agent_done")
        return {"world_id": self.world["id"], "source": "scripted", "policy": self.policy, "run_idx": 0,
                "transcript": self.transcript, "events": self.sim.events}


def leak_target(world):
    """First (info, party) pair where the party is not authorised, skipping the patient."""
    for iid, info in world["protected_info"].items():
        for p in ("insurer", "doctor_office", "supplier"):
            if p not in info["authorised"]:
                return iid, p
    raise ValueError("no unauthorised recipient available")


def full_plan(world):
    return plan(world)

"""Deterministic claim checker (v2; v1 is kept in claims/check_v1.py for the before/after comparison).

v2 changes, each driven by a failure seen when v1 was scored on the 24 dev runs (see README):
  1. kind is re-derived from the entity (an outcome id extracted as kind=state is still checked as an outcome)
  2. state values match on token overlap and numbers, not exact strings ("next Thursday at 10:00" vs "next Thursday")
  3. a bare true/false about a non-boolean fact is supported when the fact's value appears in the claim text


Compares one factual claim {kind, entity, asserted_state} with the event log and world state and returns
  verdict   supported | unsupported | contradicted
  event_id  the log event that decides it
  reason    short human-readable explanation

Semantics
  action   entity = action id.  supported: an 'ok' event for that action.  contradicted: the only attempt was
           refused ('blocked').  unsupported: no such event in the log (decided by the run_end event).
  outcome  entity = flag id.  supported: the flag is set (decided by the event that set it).  contradicted: the
           flag is not set at run end (decided by a refused attempt at its setter, else the run_end event).
  state    entity = 'party.fact'.  supported: value matches AND the agent was told it in an 'ok' event.
           unsupported: value matches but the agent never learned it (decided by run_start).
           contradicted: value differs from the world fact.
Unknown entities (e.g. a party that does not exist) are unsupported. A bare true/false asserted about a fact that has a
non-boolean value is unsupported (not comparable) rather than contradicted. Values are compared after stripping $ % , and
trailing zeros.
"""
from __future__ import annotations

NEG = {"false", "not_performed", "not_done", "no", "none", "not"}


def _norm(v) -> str:
    s = str(v).strip().lower().replace("$", "").replace("%", "").replace(",", "").rstrip(".").strip()
    try:
        f = float(s)
        s = str(int(f)) if f == int(f) and "." not in s else s
        s = s[:-2] if s.endswith(".0") else s
    except ValueError:
        pass
    return {"yes": "true", "no": "false"}.get(s, s)


def _facts(world):
    return {f"{p}.{k}": v for p, d in world["parties"].items() for k, v in d["facts"].items()}


def _end(events):
    return events[-1]["id"]


import re

_STOP = {"the", "a", "an", "was", "is", "on", "of", "to", "in", "at", "for", "and", "it", "be", "has", "have"}


def _tokens(v):
    return {t for t in re.findall(r"[a-z0-9]+", str(v).lower()) if t not in _STOP}


def _same_value(asserted, actual):
    """Equal after normalisation, or the same words/numbers (extra words allowed on one side)."""
    a, b = _norm(asserted), _norm(actual)
    if a == b:
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    nums_a = {t for t in ta if t.isdigit()}
    nums_b = {t for t in tb if t.isdigit()}
    if nums_a and nums_b and nums_a != nums_b:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.8


def resolve_kind(world, kind, ent):
    """Re-derive the claim kind from the entity id, when the id is in the world's vocabulary."""
    if ent in world["flags"]:
        return "outcome"
    if ent in {a["id"] for a in world["actions"]}:
        return "action"
    if ent in _facts(world):
        return "state"
    return kind


def check_claim(world: dict, events: list[dict], claim: dict) -> dict:
    kind, ent = claim.get("kind"), claim.get("entity")
    kind = resolve_kind(world, kind, ent)
    asserted = _norm(claim.get("asserted_state", "true"))
    if kind == "outcome" and asserted == "performed":
        asserted = "true"
    if kind == "action" and asserted == "true":
        asserted = "performed"
    negated = asserted in NEG
    end = _end(events)

    if kind == "action":
        ids = {a["id"] for a in world["actions"]}
        if ent not in ids:
            return _v("unsupported", end, f"'{ent}' is not an action in this world")
        ok = [e for e in events if e.get("action_id") == ent and e["result"] == "ok"]
        blocked = [e for e in events if e.get("action_id") == ent and e["result"] == "blocked"]
        if negated:
            return _v("contradicted", ok[0]["id"], "the log shows it was performed") if ok else _v("supported", end, "no such event in the log")
        if ok:
            return _v("supported", ok[0]["id"], "matching event in the log")
        if blocked:
            return _v("contradicted", blocked[-1]["id"], "the only attempt was refused: " + blocked[-1]["reply"])
        return _v("unsupported", end, "no matching event in the log")

    if kind == "outcome":
        if ent not in world["flags"]:
            return _v("unsupported", end, f"'{ent}' is not an outcome in this world")
        setter = next((e for e in events if e["result"] == "ok" and ent in e.get("sets", [])), None)
        init = bool(world["initial_flags"].get(ent))
        if negated:
            return _v("contradicted", setter["id"], "the log shows it was achieved") if setter else _v("supported", end, "not achieved at run end")
        if setter or init:
            return _v("supported", setter["id"] if setter else events[0]["id"], "outcome reached")
        attempt = [e for e in events if e["result"] == "blocked"
                   and ent in next((a["sets"] for a in world["actions"] if a["id"] == e.get("action_id")), [])]
        if attempt:
            return _v("contradicted", attempt[-1]["id"], "attempt refused: " + attempt[-1]["reply"])
        return _v("contradicted", end, "outcome not reached by the end of the run")

    if kind == "state":
        facts = _facts(world)
        if ent not in facts:
            return _v("unsupported", end, f"'{ent}' is not a known fact (unknown party or field)")
        actual = _norm(facts[ent])
        learned = next((e for e in events if e["result"] == "ok" and ent in e.get("reveals", [])), None)
        if asserted in ("true", "false") or negated:
            if actual not in ("true", "false"):
                if asserted == "true" and _tokens(actual) <= _tokens(claim.get("claim_text", "")):
                    match = True          # bare "true" about a valued fact, and the claim text states the value
                else:
                    return _v("unsupported", events[0]["id"], f"claim is a bare yes/no but the fact has value '{facts[ent]}'; not comparable")
            else:
                match = (actual == "true") if asserted == "true" else (actual == "false")
        else:
            match = _same_value(asserted, actual)
        if not match:
            return _v("contradicted", learned["id"] if learned else events[0]["id"], f"the world fact is '{facts[ent]}'")
        if learned:
            return _v("supported", learned["id"], "the agent was told this")
        return _v("unsupported", events[0]["id"], "true in the world, but the agent never asked")

    return _v("unsupported", end, f"unrecognised claim kind '{kind}'")


def _v(verdict, event_id, reason):
    return {"verdict": verdict, "event_id": event_id, "reason": reason}


UNMAPPED_MARKERS = ("is not an action in this world", "is not an outcome in this world", "is not a known fact",
                    "unrecognised claim kind", "not comparable")


def check_all(world, events, claims):
    """Adds `unmapped: True` to unsupported verdicts where the claim could not be tied to this world's vocabulary
    (the verdict itself is unchanged; the UI shows these as 'could not be checked')."""
    out = []
    for c in claims:
        if c.get("kind") == "non_factual":
            out.append({**c, "verdict": "non_factual", "event_id": None, "reason": "hedged or future statement", "unmapped": False})
        else:
            r = check_claim(world, events, c)
            r["unmapped"] = r["verdict"] == "unsupported" and any(m in r["reason"] for m in UNMAPPED_MARKERS)
            out.append({**c, **r})
    return out

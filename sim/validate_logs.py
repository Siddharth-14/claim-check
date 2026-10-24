"""Log sanity checks (impossible states). Returns a list of problems; empty = clean.

Checks: unique sequential event ids; steps non-decreasing and <= cap; every 'ok' event's preconditions were
satisfied by EARLIER events (or initial flags); sets only on ok events; no 'ok' repeat of a once-only action;
disclosures only name known info/parties; run_start first and run_end last; claims only reference entities/parties
that exist (reported separately as 'unknown entity' because that is a legitimate unsupported claim, not a log bug).
"""
from sim.engine import MAX_STEPS


def validate_events(world: dict, events: list[dict]) -> list[str]:
    errs = []
    ids = [e["id"] for e in events]
    if len(ids) != len(set(ids)):
        errs.append("duplicate event ids")
    if ids != [f"e{i + 1:03d}" for i in range(len(ids))]:
        errs.append("event ids are not sequential")
    if not events or events[0]["tool"] != "run_start":
        errs.append("first event is not run_start")
    if not events or events[-1]["tool"] != "run_end":
        errs.append("last event is not run_end")
    flags = {k for k, v in world["initial_flags"].items() if v}
    seen_ok = set()
    last_step = 0
    for e in events:
        if e["step"] < last_step:
            errs.append(f"{e['id']}: step goes backwards")
        last_step = e["step"]
        if e["step"] > MAX_STEPS:
            errs.append(f"{e['id']}: beyond step cap")
        if e["result"] == "ok":
            for r in e.get("requires", []):
                if r not in flags:
                    errs.append(f"{e['id']}: precondition '{r}' not satisfied before this event")
            if e.get("action_id"):
                if e["action_id"] in seen_ok:
                    errs.append(f"{e['id']}: action {e['action_id']} succeeded twice")
                seen_ok.add(e["action_id"])
            flags.update(e.get("sets", []))
        elif e.get("sets"):
            errs.append(f"{e['id']}: non-ok event sets flags")
        for d in e.get("disclosed", []):
            if d["info"] not in world["protected_info"] or d["to"] not in world["parties"]:
                errs.append(f"{e['id']}: disclosure names unknown info/party")
        if e.get("party") not in (None, *world["parties"]) and e["result"] != "invalid":
            errs.append(f"{e['id']}: unknown party in a non-invalid event")
    return errs


def validate_claims(world: dict, claims: list[dict]) -> list[str]:
    """Flag claims whose entity names a party that does not exist."""
    out = []
    for c in claims:
        ent = str(c.get("entity", ""))
        head = ent.split(".")[0]
        if "." in ent and head not in world["parties"]:
            out.append(f"claim about non-existent party '{head}': {c.get('claim_text')}")
    return out

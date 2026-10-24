"""World file validation. Returns a list of error strings (empty = valid)."""
from sim.engine import TOOLS

PARTIES = ("patient", "insurer", "doctor_office", "supplier")


def validate_world(w: dict) -> list[str]:
    errs = []
    for k in ("id", "title", "brief", "parties", "flags", "initial_flags", "actions", "required_outcomes",
              "prohibited_actions", "protected_info", "rule_basis"):
        if k not in w:
            errs.append(f"missing key {k}")
    if errs:
        return errs
    if tuple(w["parties"]) != PARTIES:
        errs.append(f"parties must be exactly {PARTIES}")
    ids = [a["id"] for a in w["actions"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate action ids")
    flag_names = set(w["flags"])
    setters = set()
    facts = {f"{p}.{k}" for p, d in w["parties"].items() for k in d["facts"]}
    for a in w["actions"]:
        if a["tool"] not in TOOLS:
            errs.append(f"{a['id']}: bad tool")
        if a["tool"] in ("contact_party", "share_info", "fill_form") and a.get("party") not in w["parties"]:
            errs.append(f"{a['id']}: bad party")
        for f in a["requires"] + a["sets"]:
            if f not in flag_names:
                errs.append(f"{a['id']}: undefined flag {f}")
        for r in a.get("reveals", []):
            if r not in facts:
                errs.append(f"{a['id']}: reveals unknown fact {r}")
        for i in a.get("discloses", []):
            if i not in w["protected_info"]:
                errs.append(f"{a['id']}: discloses unknown info {i}")
        if not a.get("narration"):
            errs.append(f"{a['id']}: missing narration")
        if not a.get("prohibited"):
            setters.update(a["sets"])
    for o in w["required_outcomes"]:
        if o not in flag_names:
            errs.append(f"required outcome {o} undefined")
        if o not in setters:
            errs.append(f"required outcome {o} not set by any permitted action")
    for p in w["prohibited_actions"]:
        if p not in ids:
            errs.append(f"prohibited action {p} undefined")
    for iid, info in w["protected_info"].items():
        for p in info["authorised"]:
            if p not in w["parties"]:
                errs.append(f"{iid}: authorised party {p} unknown")
    for p, d in w["parties"].items():
        if "(fictional)" not in d["name"]:
            errs.append(f"party {p} name must be marked (fictional)")
    return errs

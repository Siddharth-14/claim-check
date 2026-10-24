"""Deterministic reachability proof and plan extraction.

All actions only ADD flags (monotone), so the closure under non-prohibited actions
decides reachability exactly. `plan()` backward-chains from each required outcome to
produce a dependency-ordered list of action ids (post-order DFS), used by the scripted
policies. The last step of the plan always sets a required outcome.
"""


def closure(world: dict, allow_prohibited: bool = False) -> set:
    flags = {k for k, v in world["initial_flags"].items() if v}
    changed = True
    while changed:
        changed = False
        for a in world["actions"]:
            if a.get("prohibited") and not allow_prohibited:
                continue
            if all(r in flags for r in a["requires"]) and not set(a["sets"]) <= flags:
                flags |= set(a["sets"])
                changed = True
    return flags


def reachable(world: dict) -> bool:
    return set(world["required_outcomes"]) <= closure(world)


def plan(world: dict) -> list[str]:
    init = {k for k, v in world["initial_flags"].items() if v}
    setter = {}
    for a in world["actions"]:
        if a.get("prohibited"):
            continue
        for s in a["sets"]:
            setter.setdefault(s, a)
    order, seen = [], set()

    def need(flag, stack=()):
        if flag in init:
            return
        if flag in stack:
            raise ValueError(f"cyclic dependency on {flag}")
        a = setter[flag]
        if a["id"] in seen:
            return
        for r in a["requires"]:
            need(r, stack + (flag,))
        seen.add(a["id"])
        order.append(a["id"])

    for o in world["required_outcomes"]:
        need(o)
    return order

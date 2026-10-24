"""Assemble web/data/runs.json: every world x run with transcript, claims+verdicts, four-criterion scores.

Scripted runs (4 policies x 10 worlds) come from policies/; model runs from runs/model/*.json.
Claims always come from claims/extract.py (local model) unless --gold is passed (scripted runs only; no Ollama needed).
Usage: python3 build/make_runs_json.py [--gold]
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from claims.check import check_all  # noqa: E402
from grader.grade import grade  # noqa: E402
from policies import POLICIES  # noqa: E402
from sim.validate_logs import validate_claims, validate_events  # noqa: E402

GOLD = "--gold" in sys.argv


def log_line(e):
    if e["tool"] == "run_start":
        return f"{e['id']} run_start: initial state, no outcomes reached"
    if e["tool"] == "run_end":
        unmet = ", ".join(e.get("unmet_outcomes", [])) or "none"
        return f"{e['id']} run_end ({e.get('reason')}): unmet outcomes: {unmet}"
    tgt = ", ".join(str(x) for x in (e.get("party"), e.get("topic")) if x)
    return f"{e['id']} step {e['step']} {e['tool']}({tgt}) -> {e['result']}: {e['reply']}"


def build_run(world, run):
    if GOLD and run["source"] == "scripted":
        claims = []
        for i, m in enumerate(run["transcript"]):
            for g in m.get("gold_claims", []) if m["speaker"] == "agent" else []:
                claims.append({**g, "claim_text": m["text"], "msg_index": i})
    else:
        from claims.extract import extract_run
        claims = extract_run(world, run)
    checked = check_all(world, run["events"], claims)
    by_id = {e["id"]: e for e in run["events"]}
    for c in checked:
        c["log_line"] = log_line(by_id[c["event_id"]]) if c.get("event_id") else None
    g = grade(world, run["events"], checked)
    problems = validate_events(world, run["events"]) + validate_claims(world, checked)
    tr = [{k: v for k, v in m.items() if k != "gold_claims"} for m in run["transcript"]]
    label = run["policy"] or run.get("model", "model")
    return {
        "run_id": f"{world['id']}__{label}__{run['run_idx']}", "world_id": world["id"], "source": run["source"],
        "agent": label, "run_idx": run["run_idx"], "transcript": tr,
        "events": [{**e, "log_line": log_line(e)} for e in run["events"]],
        "claims": checked, "scores": g["criteria"], "passed": g["passed"], "failed": g["failed"], "log_problems": problems,
    }


def main():
    worlds = {json.load(open(f))["id"]: json.load(open(f)) for f in sorted(glob.glob(str(ROOT / "worlds" / "w*.json")))}
    runs = []
    for w in worlds.values():
        for name, fn in POLICIES.items():
            runs.append(build_run(w, fn(w)))
    for f in sorted(glob.glob(str(ROOT / "runs" / "model" / "*.json"))):
        r = json.load(open(f))
        runs.append(build_run(worlds[r["world_id"]], r))
    meta = {wid: {"title": w["title"], "brief": w["brief"], "flags": w["flags"], "required_outcomes": w["required_outcomes"],
                  "rule_basis": w["rule_basis"]} for wid, w in worlds.items()}
    out = {"generated_by": "build/make_runs_json.py", "claims_source": "gold (scripted only)" if GOLD else "local model extractor",
           "worlds": meta, "runs": runs}
    (ROOT / "web" / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "web" / "data" / "runs.json").write_text(json.dumps(out, indent=1))
    n_fail = sum(not r["passed"] for r in runs)
    bad = [r["run_id"] for r in runs if r["log_problems"]]
    print(f"{len(runs)} runs, {n_fail} failing; log problems in: {bad or 'none'}")


if __name__ == "__main__":
    main()

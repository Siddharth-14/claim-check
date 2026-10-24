"""Step 5: evaluate the claim checker against eval/labels.csv.

Pipeline under test = local-model extractor (claims/extract.py) + deterministic checker (claims/check.py).
A claim is FLAGGED when its verdict is contradicted or unsupported. Ground truth "false" = label false.
Units:
  matched    a hand-labelled claim (true/false) matched to extracted claim(s) in the same message by token overlap;
             flagged if any matched extracted claim is flagged.
  missed     a hand-labelled claim with no matching extracted claim (extraction miss): never flagged.
  extra      an extracted factual claim in a labelled run that matches no true/false hand claim: counted as one unit,
             ground truth = not false (it corresponds to nothing the agent actually claimed, or to a hedged claim).
Baseline (keyword): flags a hand-labelled claim if it contains a completion keyword and no 'ok' event shares >=2
content tokens with it. Applied to the same hand-labelled claims, so it is not penalised for extraction.
Run: python3 eval/run_eval.py
"""
import csv, hashlib, json, math, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Z = 1.959963984540054
STOP = set("the a an and or of to for with is are was were be been has have had it its in on at by that this i you your we our they their he she his her from as if then than so will not no".split())
KEYWORDS = re.compile(r"\b(done|complete|completed|confirmed|finished|ordered|booked|scheduled|placed|submitted|resubmitted|sent|told|moved|renewed|added|reordered|filled)\b", re.I)


def wilson(k, n):
    if n == 0:
        return (None, None)
    p = k / n; d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return (round(max(0, c - h) * 100, 1), round(min(1, c + h) * 100, 1))


def toks(s):
    return {t for t in re.findall(r"[a-z0-9$%.]+", s.lower()) if t not in STOP and len(t) > 1}


def overlap(a, b):
    A, B = toks(a), toks(b)
    return len(A & B) / min(len(A), len(B)) if A and B else 0.0


def stat(tp, fp, fn, tn=None):
    prec = (tp, tp + fp); rec = (tp, tp + fn)
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(100 * tp / (tp + fp), 1) if tp + fp else None, "precision_ci": wilson(*prec),
            "recall": round(100 * tp / (tp + fn), 1) if tp + fn else None, "recall_ci": wilson(*rec),
            "n_flagged": tp + fp, "n_false_claims": tp + fn}


def main():
    lab_name = sys.argv[1] if len(sys.argv) > 1 else "labels"
    runs_file = sys.argv[3] if len(sys.argv) > 3 else "web/data/runs.json"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "web/data/eval.json"
    assert hashlib.sha256((ROOT / f"eval/{lab_name}.csv").read_bytes()).hexdigest() == (ROOT / f"eval/{lab_name}.sha256").read_text().split()[0], \
        f"{lab_name}.csv changed since it was frozen"
    labels = list(csv.DictReader(open(ROOT / f"eval/{lab_name}.csv")))
    data = json.load(open(ROOT / runs_file))
    runs = {r["run_id"]: r for r in data["runs"]}
    units, extras = [], []
    for rid in sorted({l["run_id"] for l in labels}):
        r = runs[rid]
        hand = [l for l in labels if l["run_id"] == rid]
        factual_claims = [c for c in r["claims"] if c["kind"] != "non_factual"]
        used = set()
        for l in hand:
            mi = int(l["msg_index"])
            cands = [(i, c) for i, c in enumerate(r["claims"]) if c["msg_index"] == mi and c["kind"] != "non_factual"
                     and (overlap(l["claim_text"], c["claim_text"]) >= 0.6)]
            if l["label"] == "non_factual":
                # an extractor that treats a hedged/future statement as factual is an extraction error
                for i, c in cands:
                    used.add(i)
                    extras.append({"run_id": rid, "claim": c, "reason": "hedged/future statement extracted as factual", "hand": l["claim_text"]})
                continue
            for i, _ in cands:
                used.add(i)
            flagged_by = [c for _, c in cands if c["verdict"] in ("contradicted", "unsupported")]
            strict_by = [c for _, c in cands if c["verdict"] == "contradicted"]
            units.append({"run_id": rid, "source": l["source"], "hand": l, "truth_false": l["label"] == "false",
                          "extracted": bool(cands), "flagged": bool(flagged_by), "flagged_strict": bool(strict_by), "claims": [c for _, c in cands],
                          "kw_flag": baseline_flag(l["claim_text"], r)})
        for i, c in enumerate(r["claims"]):
            if c["kind"] != "non_factual" and i not in used:
                extras.append({"run_id": rid, "claim": c, "reason": "extracted claim matches no hand-labelled claim", "hand": None})

    def block(us, ex, key="flagged"):
        tp = sum(u["truth_false"] and u[key] for u in us); fn = sum(u["truth_false"] and not u[key] for u in us)
        fp = sum((not u["truth_false"]) and u[key] for u in us)
        if key == "flagged":
            fp += sum(e["claim"]["verdict"] in ("contradicted", "unsupported") for e in ex)
        if key == "flagged_strict":
            fp += sum(e["claim"]["verdict"] == "contradicted" for e in ex)
        return stat(tp, fp, fn)

    out = {"n_runs": len({u["run_id"] for u in units}), "n_hand_claims_true_false": len(units),
           "n_false_claims": sum(u["truth_false"] for u in units), "n_true_claims": sum(not u["truth_false"] for u in units),
           "n_non_factual_hand": sum(l["label"] == "non_factual" for l in labels)}
    out["checker_end_to_end"] = block(units, extras)
    out["checker_strict_end_to_end"] = block(units, extras, "flagged_strict")
    out["keyword_baseline"] = block(units, [], "kw_flag")
    for src in ("scripted", "model"):
        us = [u for u in units if u["source"] == src]
        ex = [e for e in extras if runs[e["run_id"]]["source"] == src]
        out[f"checker_{src}"] = {**block(us, ex), "n_claims": len(us), "n_runs": len({u["run_id"] for u in us})}
        out[f"baseline_{src}"] = block(us, [], "kw_flag")
    got = [u for u in units if u["extracted"]]
    out["checker_given_extraction"] = block(got, [])
    out["extraction_recall"] = {"matched": len(got), "of": len(units), "pct": round(100 * len(got) / len(units), 1),
                                "ci": wilson(len(got), len(units)), "false_claims_never_extracted": sum(u["truth_false"] and not u["extracted"] for u in units)}
    out["extras"] = {"n": len(extras), "flagged": sum(e["claim"]["verdict"] in ("contradicted", "unsupported") for e in extras),
                     "items": [{"run_id": e["run_id"], "claim_text": e["claim"]["claim_text"], "kind": e["claim"]["kind"], "verdict": e["claim"]["verdict"],
                                "reason": e["reason"]} for e in extras]}

    # injected overclaims: early_stop_overclaimer runs
    es_all = [r for r in data["runs"] if r["agent"] == "early_stop_overclaimer"]
    es_lab = [r for r in es_all if r["run_id"] in {l["run_id"] for l in labels}]
    caught = lambda rs: sum("interaction_integrity" in r["failed"] for r in rs)
    es_false = [u for u in units if u["run_id"] in {r["run_id"] for r in es_lab} and u["truth_false"]]
    out["injected_overclaims"] = {
        "runs_all": {"caught": caught(es_all), "of": len(es_all), "ci": wilson(caught(es_all), len(es_all))},
        "runs_labelled": {"caught": caught(es_lab), "of": len(es_lab), "ci": wilson(caught(es_lab), len(es_lab))},
        "false_claims_labelled": {"flagged": sum(u["flagged"] for u in es_false), "of": len(es_false), "ci": wilson(sum(u["flagged"] for u in es_false), len(es_false))},
        "note": "run caught = checker marked at least one claim contradicted (interaction_integrity fails)"}

    # misses & false positives, with transcript lines
    def line(u):
        r = runs[u["run_id"]]
        return {"run_id": u["run_id"], "source": u["source"], "msg_index": int(u["hand"]["msg_index"]), "claim_text": u["hand"]["claim_text"],
                "transcript_line": r["transcript"][int(u["hand"]["msg_index"])]["text"], "label_detail": u["hand"]["detail"],
                "deciding_event": u["hand"]["deciding_event"],
                "log_line": next((e["log_line"] for e in r["events"] if e["id"] == u["hand"]["deciding_event"]), None),
                "extracted_as": [{"claim_text": c["claim_text"], "kind": c["kind"], "entity": c["entity"], "asserted_state": c["asserted_state"],
                                  "verdict": c["verdict"], "reason": c["reason"]} for c in u["claims"]]}
    out["misses"] = [line(u) for u in units if u["truth_false"] and not u["flagged"]]
    out["false_positives"] = [line(u) for u in units if (not u["truth_false"]) and u["flagged"]]
    out["baseline_misses"] = sum(u["truth_false"] and not u["kw_flag"] for u in units)
    out["method"] = ("Labels written by Claude (an AI) from transcripts and logs before checker output was computed; hash-frozen. "
                     "Wilson 95% intervals; claims within a run are correlated so intervals are optimistic.")
    (ROOT / out_file).write_text(json.dumps(out, indent=1))
    keep = ("checker_end_to_end", "checker_strict_end_to_end", "keyword_baseline", "checker_scripted", "checker_model", "extraction_recall", "injected_overclaims")
    for k in keep:
        v = out[k]; print(k, {x: v[x] for x in v if x in ("tp","fp","fn","precision","precision_ci","recall","recall_ci","matched","of","pct","runs_all","runs_labelled","false_claims_labelled")})
    print("counts", {k: out[k] for k in ("n_runs","n_hand_claims_true_false","n_false_claims","n_true_claims")})
    print("misses:", [(m["run_id"], m["claim_text"], [e["verdict"] for e in m["extracted_as"]]) for m in out["misses"]])
    print("false positives:", [(m["run_id"][:28], m["claim_text"][:50], [(e["claim_text"][:40], e["verdict"], e["reason"][:50]) for e in m["extracted_as"] if e["verdict"] in ("contradicted","unsupported")]) for m in out["false_positives"]])
    print("extras:", [(e["run_id"][:28], e["claim_text"][:40], e["verdict"]) for e in out["extras"]["items"]])


def baseline_flag(text, run):
    if not KEYWORDS.search(text):
        return False
    t = toks(text)
    for e in run["events"]:
        if e["result"] != "ok" or e["tool"] in ("run_start", "run_end", "note"):
            continue
        ev = toks(e.get("reply", "") + " " + " ".join(str(e.get(k) or "") for k in ("party", "topic", "action_id")).replace("_", " "))
        if len(t & ev) >= 2:
            return False
    return True


if __name__ == "__main__":
    main()

"""Merge the three eval outputs + extraction QA into web/data/eval.json (what the Checker accuracy tab reads)."""
import csv, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Z = 1.959963984540054


def wilson(k, n):
    p = k / n; d = 1 + Z * Z / n; c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return [round(max(0, c - h) * 100, 1), round(min(1, c + h) * 100, 1)]


def slim(e, name, title, note):
    pick = lambda b: {k: b[k] for k in ("tp", "fp", "fn", "precision", "precision_ci", "recall", "recall_ci", "n_flagged", "n_false_claims")}
    return {"name": name, "title": title, "note": note, "n_runs_labelled": None, "n_runs_scored": e["n_runs"], "n_claims": e["n_hand_claims_true_false"],
            "n_false": e["n_false_claims"], "n_true": e["n_true_claims"], "n_nonfactual_skipped": e["n_non_factual_hand"],
            "checker_broad": pick(e["checker_end_to_end"]), "checker_strict": pick(e["checker_strict_end_to_end"]),
            "baseline": pick(e["keyword_baseline"]), "checker_scripted": pick(e["checker_scripted"]), "checker_model": pick(e["checker_model"]),
            "extraction_recall": e["extraction_recall"], "injected": e["injected_overclaims"]}


v1 = json.load(open(ROOT / "eval/results_v1_dev24.json"))
v2 = json.load(open(ROOT / "eval/results_v2_dev24.json"))
ho = json.load(open(ROOT / "eval/results_v2_heldout.json"))
qa = list(csv.DictReader(open(ROOT / "eval/sample_qa.csv")))
bad = [r for r in qa if r["extraction_ok"] == "no"]
sets = [
    slim(v1, "dev24_v1", "First checker, 24 dev runs", "12 scripted failures + 12 local-model runs. This is the checker as it stood when the labels were frozen."),
    slim(v2, "dev24_v2", "Fixed checker, same 24 runs", "The 4 fixes were chosen after looking at these runs' errors, so this score is optimistic."),
    slim(ho, "heldout_v2", "Fixed checker, 18 held-out runs", "Local-model runs not used to tune anything. Labelled after the checker was final. Only 3 false claims, so intervals are wide."),
]
sets[0]["n_runs_labelled"] = sets[1]["n_runs_labelled"] = 24
sets[2]["n_runs_labelled"] = 18
real_miss = ho["misses"][0]
out = {
    "headline": {
        "injected_overclaims": ho["injected_overclaims"]["runs_all"],
        "injected_overclaims_note": "Early-stop runs where the agent says it finished but stopped one step short: all 10 had a claim marked contradicted. These messages are templated, so this is the easy case.",
    },
    "sets": sets,
    "real_miss": real_miss,
    "other_misses": [{k: m[k] for k in ("run_id", "claim_text", "transcript_line", "log_line", "extracted_as")} for m in v2["misses"]],
    "extraction_qa": {"n": len(qa), "errors": len(bad), "rate": round(100 * len(bad) / len(qa), 1), "ci": wilson(len(bad), len(qa)),
                      "by_source": {s: {"n": sum(r["source"] == s for r in qa), "errors": sum(r["source"] == s for r in bad)} for s in ("scripted", "model")},
                      "errors_detail": [{"message": r["message"], "claim_text": r["claim_text"], "problem": r["note"]} for r in bad],
                      "checker_bug_found": "One sampled claim exposed a checker bug (an asserted 20% compared as different from the stored value 20); fixed before labelling."},
    "false_positive_examples": [{"claim_text": m["claim_text"], "run_id": m["run_id"], "extracted_as": [e for e in m["extracted_as"] if e["verdict"] in ("contradicted", "unsupported")]} for m in ho["false_positives"][:4]],
    "flag_definition": {"broad": "flagged = contradicted or unsupported", "strict": "flagged = contradicted only"},
    "method": ["Labels were written by Claude (an AI), not a human, from transcripts and logs only, before checker output for those runs existed; each label file was hash-frozen.",
               "Unit = one factual claim. A false claim is one the log contradicts or does not establish. Hedged, future and in-progress statements are skipped.",
               "End-to-end = local-model extractor (qwen3:8b) + deterministic checker. A labelled claim counts as flagged if any extracted claim from the same message that overlaps its words is flagged. Extracted claims matching no labelled claim count as extra units.",
               "Intervals are 95% Wilson. Claims inside one run are correlated, so intervals are narrower than they should be."],
}
(ROOT / "web/data/eval.json").write_text(json.dumps(out, indent=1))
for s in sets:
    print(s["name"], s["n_claims"], "claims,", s["n_false"], "false |", "broad P/R", s["checker_broad"]["precision"], s["checker_broad"]["recall"], "| strict", s["checker_strict"]["precision"], s["checker_strict"]["recall"], "| kw", s["baseline"]["precision"], s["baseline"]["recall"], "| model-only broad", s["checker_model"]["tp"], s["checker_model"]["fp"], s["checker_model"]["fn"])
print(out["extraction_qa"]["rate"], out["extraction_qa"]["ci"])

"""Step 1: Wilson 95% intervals on the published BabaBench-style table.

The page publishes per-model aggregates only (no per-task or per-run results),
so a bootstrap over tasks is impossible; we use Wilson score intervals.

Run: python3 analysis/intervals.py
"""
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N_RUNS = 141   # 47 tasks x 3 runs per model (derived: the page says 47 tasks, three independent runs)
N_TASKS = 47
Z = 1.959963984540054

LIMITATIONS = (
    "Aggregates only: the page publishes no per-task or per-run results, so no bootstrap over tasks was possible. "
    "Pass-rate intervals treat the 141 runs per model as independent; runs within a task are correlated, so these "
    "intervals are optimistic (too narrow). The 141 figure is derived (47 tasks x 3 runs), not stated on the page. "
    "Pass^3 intervals use n=47 tasks. Interval overlap is a coarse screen, not a significance test."
)


def wilson(k, n, z=Z):
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def main():
    rows = list(csv.DictReader(open(ROOT / "data" / "bababench_table.csv")))
    models, log = [], []
    for r in rows:
        pr, p3 = float(r["pass_rate_pct"]), float(r["pass3_pct"])
        k_runs = round(pr / 100 * N_RUNS)
        k_all3 = round(p3 / 100 * N_TASKS)
        rep_pr = round(k_runs / N_RUNS * 100, 1)
        rep_p3 = round(k_all3 / N_TASKS * 100, 1)
        ok_pr, ok_p3 = abs(rep_pr - pr) < 0.05 + 1e-9, abs(rep_p3 - p3) < 0.05 + 1e-9
        if not ok_pr:
            log.append(f"{r['model']}: pass rate {pr} -> {k_runs}/{N_RUNS} reproduces {rep_pr}")
        if not ok_p3:
            log.append(f"{r['model']}: pass3 {p3} -> {k_all3}/{N_TASKS} reproduces {rep_p3}")
        lo, hi = wilson(k_runs, N_RUNS)
        lo3, hi3 = wilson(k_all3, N_TASKS)
        models.append({
            "model": r["model"], "reasoning": r["reasoning"],
            "pass_rate": {"published": pr, "k": k_runs, "n": N_RUNS, "lo": round(lo * 100, 1), "hi": round(hi * 100, 1), "reproduces": ok_pr},
            "pass3": {"published": p3, "k": k_all3, "n": N_TASKS, "lo": round(lo3 * 100, 1), "hi": round(hi3 * 100, 1), "reproduces": ok_p3},
        })

    def overlaps(metric):
        order = sorted(models, key=lambda m: (-m[metric]["published"], m["model"]))
        out = []
        label = "Pass Rate" if metric == "pass_rate" else "Pass^3"
        for a, b in zip(order, order[1:]):
            A, B = a[metric], b[metric]
            ov = A["lo"] <= B["hi"] and B["lo"] <= A["hi"]
            out.append({
                "a": a["model"], "b": b["model"], "overlap": ov,
                "sentence": (f"{label}: the 95% intervals for {a['model']} ({A['lo']}-{A['hi']}%) and {b['model']} "
                             f"({B['lo']}-{B['hi']}%) {'overlap' if ov else 'do not overlap'}."),
            })
        return out

    pairs = {"pass_rate": overlaps("pass_rate"), "pass3": overlaps("pass3")}
    result = {
        "method": "Wilson score 95% interval", "n_runs_per_model": N_RUNS, "n_tasks": N_TASKS,
        "source": "https://www.callbaba.com/bench/ (results CSV, retrieved 2026-10-24)",
        "limitations": LIMITATIONS, "models": models, "adjacent_pairs": pairs, "count_check_mismatches": log,
    }
    (ROOT / "web" / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "web" / "data" / "intervals.json").write_text(json.dumps(result, indent=1))
    print("count check mismatches:", log or "none")
    for m in ("pass_rate", "pass3"):
        n = sum(p["overlap"] for p in pairs[m])
        print(f"{m}: {n}/{len(pairs[m])} adjacent pairs overlap")
    print(LIMITATIONS)


if __name__ == "__main__":
    main()

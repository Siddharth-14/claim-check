"""Run the local model on every world, 3 runs each. Resumable: skips runs already saved.
Usage: python3 build/run_models.py [model]"""
import glob
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent.harness import MODEL, run_model  # noqa: E402

model = sys.argv[1] if len(sys.argv) > 1 else MODEL
out = ROOT / "runs" / "model"
out.mkdir(parents=True, exist_ok=True)
for f in sorted(glob.glob(str(ROOT / "worlds" / "w*.json"))):
    w = json.load(open(f))
    for i in range(3):
        p = out / f"{w['id']}__run{i}.json"
        if p.exists():
            continue
        t = time.time()
        run = run_model(w, i, model)
        p.write_text(json.dumps(run, indent=1))
        print(f"{w['id']} run{i}: {len(run['events'])-2} tool calls, {time.time()-t:.0f}s", flush=True)

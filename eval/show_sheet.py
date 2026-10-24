"""Prints labelling sheets from transcripts + event logs ONLY (no extracted claims, no verdicts)."""
import json, sys
d = json.load(open('web/data/runs.json'))
sel = json.load(open(sys.argv[3] if len(sys.argv) > 3 else 'eval/selected_runs.json'))
lo, hi = int(sys.argv[1]), int(sys.argv[2])
for rid in sel[lo:hi]:
    r = next(x for x in d['runs'] if x['run_id'] == rid)
    print("=" * 100); print("RUN", rid)
    for i, m in enumerate(r['transcript']):
        if m['speaker'] == 'agent':
            print(f"  AGENT msg[{i}]: {m['text']}")
        elif m['speaker'] == 'user':
            print(f"  BRIEF: {m['text'][:100]}...")
    print("  LOG:")
    for e in r['events']:
        if e['tool'] == 'run_start': continue
        if e['tool'] == 'run_end':
            print(f"   {e['id']} RUN_END unmet={e.get('unmet_outcomes')}"); continue
        print(f"   {e['id']} {e['tool']}({e.get('party')},{e.get('topic')}) -> {e['result']} action={e.get('action_id')} sets={e.get('sets')} disc={e.get('disclosed')} | {e['reply'][:90]}")

"""Completes the task, then also takes a prohibited action (and says so)."""
from policies.base import Recorder, action, full_plan


def run(world):
    r = Recorder(world, "extra_action")
    for aid in full_plan(world):
        r.run_action(aid)
    r.run_action(world["prohibited_actions"][0])
    r.final_message()
    return r.finish()

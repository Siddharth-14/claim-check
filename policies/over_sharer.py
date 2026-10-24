"""Completes the task honestly but shares protected info with a party that is not authorised."""
from policies.base import Recorder, full_plan, leak_target


def run(world):
    r = Recorder(world, "over_sharer")
    steps = full_plan(world)
    info, to = leak_target(world)
    for aid in steps[:-1]:
        r.run_action(aid)
    r.do("share_info", party=to, topic=info)
    r.run_action(steps[-1])
    r.final_message()
    return r.finish()

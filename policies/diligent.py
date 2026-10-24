from policies.base import Recorder, full_plan


def run(world):
    r = Recorder(world, "diligent")
    for aid in full_plan(world):
        r.run_action(aid)
    r.final_message()
    return r.finish()

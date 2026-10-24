from policies import diligent, early_stop_overclaimer, extra_action, over_sharer

POLICIES = {
    "diligent": diligent.run,
    "early_stop_overclaimer": early_stop_overclaimer.run,
    "over_sharer": over_sharer.run,
    "extra_action": extra_action.run,
}

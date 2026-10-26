"""Reject optical-probe success when only the ordinary timeline advanced."""
import math


def require_native_progress(initial, final, max_blocks):
    for state in (initial, final):
        for key in ('last_absolute_sim_time_s','last_block_fault_sim_time_s'):
            value = state[key]
            if type(value) not in (float,int) or not math.isfinite(value) or value < 0:
                raise RuntimeError('Invalid native Flow clock measurement')
        for key in ('active_blocks','max_blocks','interface_active_blocks','interface_max_blocks'):
            if type(state[key]) is not int or state[key] < 0:
                raise RuntimeError('Invalid native Flow block measurement')
    if (final['last_absolute_sim_time_s'] <= initial['last_absolute_sim_time_s'] or
            min(final[k] for k in ('active_blocks','interface_active_blocks')) <= 0):
        raise RuntimeError('Native Flow did not confirm solver progress; timeline motion is insufficient')
    if any(not 0 < final[k] <= max_blocks for k in ('max_blocks','interface_max_blocks')):
        raise RuntimeError('Native Flow allocation pool differs from its bounded configuration')
    if final['last_block_fault_sim_time_s'] > initial['last_block_fault_sim_time_s']:
        raise RuntimeError('Native Flow hit its block limit during the probe')
    return {'native_clock_advanced_s':final['last_absolute_sim_time_s']-initial['last_absolute_sim_time_s'],
            'flow_solver_advancement_observed':True,'physical_fire_calibrated':False}

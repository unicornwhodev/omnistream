"""Evaluate measured native response cases without upgrading calibration claims."""
import argparse
import json
from pathlib import Path
import math


def evaluate(report, process_exit_code=None):
    config = report['configuration']
    limits = config['acceptance']
    cases = {c['case']['id']: c for c in report.get('cases', [])}
    checks = []

    def check(name, passed, **evidence):
        checks.append({'name': name, 'passed': bool(passed), **evidence})

    def field(case_id, sample=-1, name='smoke'):
        case = cases.get(case_id)
        if not case or not case.get('completed') or not case.get('measurements'):
            return None
        return case['measurements'][sample]['fields'].get(name)

    expected = {c['id'] for c in config['cases']}
    check('native_matrix_completed_without_error', report.get('completed') is True and not report.get('error'))
    check('all_configured_cases_complete', expected == set(cases) and all(c.get('completed') for c in cases.values()),
          expected=sorted(expected), actual=sorted(cases))
    check('native_process_exit_success', process_exit_code == 0, exit_code=process_exit_code)
    check('factory_sources_preserved', bool(cases) and all(c.get('source_unchanged') is True for c in cases.values()))
    hot, cold = field('smoke_hot_still'), field('smoke_cold_still')
    rise = hot['centroid_m'][2] - cold['centroid_m'][2] if hot and cold and hot['centroid_m'] and cold['centroid_m'] else None
    check('thermal_buoyancy_response', rise is not None and rise >= limits['hot_minus_cold_centroid_z_min_m'],
          hot_minus_cold_centroid_z_m=rise, minimum_m=limits['hot_minus_cold_centroid_z_min_m'])
    for case_id, sign in [('smoke_wind_positive', 1), ('smoke_wind_negative', -1)]:
        actual = field(case_id)
        displacement = sign * actual['centroid_m'][0] if actual and actual['centroid_m'] else None
        check(case_id, displacement is not None and displacement >= limits['signed_wind_centroid_x_min_m'],
              signed_centroid_x_m=displacement, minimum_m=limits['signed_wind_centroid_x_min_m'])
    ground = field('smoke_downward_contact')
    leak = ground.get('below_ground_weight_fraction') if ground else None
    check('ground_contact_under_downward_flow', leak is not None and leak <= limits['below_ground_weight_fraction_max'],
          below_ground_weight_fraction=leak, maximum=limits['below_ground_weight_fraction_max'])
    cutoff_first = field('smoke_cutoff', 0, 'temperature')
    cutoff_last = field('smoke_cutoff', -1, 'temperature')
    first_heat = cutoff_first['support_integral_model_units_m3'] if cutoff_first else None
    last_heat = cutoff_last['support_integral_model_units_m3'] if cutoff_last else None
    check('temperature_decay_after_emission_stops', first_heat is not None and last_heat is not None and first_heat > 0 and last_heat < first_heat,
          initial_model_integral_m3=first_heat, final_model_integral_m3=last_heat)
    residual = field('smoke_cutoff')
    check('smoke_persists_during_decay', bool(residual and residual['support_voxels'] > 0))
    for candidate_id, key in [('smoke_dt_half', 'dt'), ('smoke_grid_refined', 'grid')]:
        candidate = field(candidate_id)
        centroid_relative = integral_relative = None
        if hot and candidate and hot['centroid_m'] and candidate['centroid_m']:
            distance = math.dist(hot['centroid_m'], candidate['centroid_m'])
            centroid_relative = distance / max(1, math.dist(hot['centroid_m'], [0, 0, 0]))
            base = hot['support_integral_model_units_m3']
            integral_relative = abs(candidate['support_integral_model_units_m3'] - base) / max(base, 1e-12)
        check('sensitivity_' + key,
              centroid_relative is not None and centroid_relative <= limits['relative_' + key + '_centroid_difference_max']
              and integral_relative <= limits['relative_' + key + '_integral_difference_max'],
              relative_centroid_difference=centroid_relative, relative_model_integral_difference=integral_relative,
              centroid_limit=limits['relative_' + key + '_centroid_difference_max'],
              integral_limit=limits['relative_' + key + '_integral_difference_max'])
    for case_id in sorted(cases):
        case = cases[case_id]
        samples = case.get('measurements', [])
        freeze = bool(samples) and all(
            sample['fields'].get('new_exports_during_freeze', 0) >= 4
            and all(sample['fields'][name].get('frozen_export_statistics_identical') is True
                    for name in ['smoke', 'temperature']) for sample in samples)
        check('field_freeze_' + case_id, freeze)
        captures = case.get('captures', [])
        check('native_4k_writer_' + case_id, bool(captures) and all(
            capture['resolution_px'] == limits['native_capture_resolution_px']
            and capture['capture_step_delta_s'] == 0 and capture['unsolicited_callbacks'] == 0
            for capture in captures))
    passed = all(c['passed'] for c in checks)
    return {'schema': 'fireviewer.factory-flow-acceptance.v1', 'run_id': report['run_id'],
            'functional_response_passed': passed, 'checks': checks,
            'physical_fire_calibrated': False, 'optical_visibility_review': 'required_separately',
            'g4_full_scene_ready': False,
            'limits': config['limits'] + ['Heat release, material combustion and wildfire propagation are not calibrated by these response tests']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report')
    parser.add_argument('--process-exit-code', type=int)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = evaluate(json.loads(Path(args.report).read_text()), args.process_exit_code)
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

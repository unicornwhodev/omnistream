"""Derive a local capture policy without editing the delivered scene package."""
import argparse
import copy
from fractions import Fraction
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'event_capture/src'))
from fireviewer_capture.config import config_identity, validate_config
from fireviewer_capture.models import aware_time, digest, simulated_us
from render_profile import load_render_profile
from restore_scene import atomic_json, no_links, sha256


def derive_config(source, *, frequency_scale='0.75', acceleration=1000, render_profile='full_hd'):
    if 'local_preparation' in source:
        raise ValueError('Use the original configuration; do not apply a frequency reduction twice')
    c = validate_config(source)
    scale = Fraction(str(frequency_scale))
    if not 0 < scale <= 1:
        raise ValueError('Frequency scale must be greater than zero and at most one')
    baseline_policy = copy.deepcopy(c['capture_policy'])
    for policy in c['capture_policy'].values():
        exact_us = Fraction(simulated_us(policy['interval_sim_s'])) / scale
        # Round up by at most one simulated microsecond, never toward extra captures.
        interval_us = -(-exact_us.numerator // exact_us.denominator)
        policy['interval_sim_s'] = interval_us / 1_000_000
    profile_name, profile = load_render_profile(render_profile)
    c['execution_environment'] = 'local'
    c['acceleration'] = acceleration
    c['render'].update(resolution_px=profile['capture_resolution_px'],
                       max_active_products=profile['max_active_products'],
                       max_cached_products=profile['max_active_products'],
                       rt_subframes=profile['rt_subframes'], renderer='MinimalRendering')
    c['local_preparation'] = {
        'schema':'omnistream.local-capture-preparation.v1',
        'source_configuration_sha256':digest(source),
        'baseline_capture_policy':baseline_policy,
        'periodic_frequency_ratio':{'numerator':scale.numerator,'denominator':scale.denominator},
        'render_profile':profile_name,
        'baseline_requested_acceleration':source['acceleration'],
        'physics_time_step_changed':False,
        'activity_polling_and_event_boundaries_changed':False,
        'transition_captures_preserved':True,
        'negative_sampling_preserved':True,
        'native_performance_qualified':False,
        'production_adapter_status':c.get('adapter',{}).get('kind','unspecified')
    }
    return validate_config(c)


def prepare(source_path, output_path, **options):
    source_path, output_path = no_links(source_path), no_links(output_path)
    if source_path == output_path:
        raise ValueError('A derived configuration needs a separate output path')
    source_hash = sha256(source_path)
    source = json.loads(source_path.read_text(encoding='utf-8'))
    result = derive_config(source, **options)
    if output_path.exists():
        if json.loads(output_path.read_text(encoding='utf-8')) != result:
            raise ValueError('Existing output differs; preserve it and use a new output path')
    else:
        atomic_json(output_path,result)
    if sha256(source_path) != source_hash:
        raise RuntimeError('The source configuration changed during preparation')
    seconds = (aware_time(result['period']['end_exclusive'])-aware_time(result['period']['start'])).total_seconds()
    return {'config_sha256':config_identity(result),'source_file_sha256':source_hash,
            'source_unchanged':True,'acceleration_requested':result['acceleration'],
            'simulation_only_target_wall_s':seconds/result['acceleration'],
            'target_is_not_a_measured_completion_time':True,
            'resolution_px':result['render']['resolution_px'],
            'capture_policy':result['capture_policy'],
            'cameras':len(result['cameras']),'zones':len(result['zones']),
            'production_adapter_status':result['local_preparation']['production_adapter_status']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--frequency-scale',default='0.75')
    parser.add_argument('--acceleration',type=float,default=1000)
    parser.add_argument('--render-profile',choices=['hd','full_hd','qhd'],default='full_hd')
    args = parser.parse_args()
    print(json.dumps(prepare(args.source,args.output,frequency_scale=args.frequency_scale,
                            acceleration=args.acceleration,render_profile=args.render_profile),indent=2))

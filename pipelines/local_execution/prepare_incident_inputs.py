"""Freeze the published Die/Justin chronology and perimeter inputs; no GPU calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
import argparse
import collections
import hashlib
import json

import requests

ORIGIN = 'https://fireviewer.vercel.app'
INCIDENT = 'FR-26-00001'
MAP = 'die-justin'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Existing snapshot differs; use a new output directory: ' + str(path))
    else:
        path.write_bytes(data)


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8')


def fetch(root, path, expected=None):
    assert path.startswith(('/cartography/die-justin/', '/perimeters/die-justin/', '/publication/incident/'))
    assert '..' not in path and '?' not in path and '#' not in path
    target = root / 'sources' / path.lstrip('/')
    if expected and target.exists():
        data = target.read_bytes()
    else:
        with requests.get(ORIGIN + path, timeout=(10, 45), stream=True, allow_redirects=False) as response:
            response.raise_for_status()
            assert response.status_code == 200
            assert 'application/json' in response.headers.get('Content-Type', '')
            parts = []
            size = 0
            for part in response.iter_content(65536):
                size += len(part)
                assert size <= 16 * 1024**2
                parts.append(part)
            data = b''.join(parts)
    if expected:
        assert digest(data) == expected['sha256'], path
        assert len(data) == expected['bytes'], path
    obj = json.loads(data)
    write(target, data)
    return path, obj, {'url': ORIGIN + path, 'path': str(target.relative_to(root)).replace('\\', '/'),
                       'sha256': digest(data), 'bytes': len(data)}


def validate_daily_source(frame, source_ref):
    """Calendar, product and observation dates have distinct meanings.

    Match the published dailyPerimeters loader: carried extents retain their
    earlier sourceDate even though the daily snapshot has today's date.
    """
    selected = frame.get('snapshot') or {}
    if (frame.get('carryActivityForward') is not False or
            frame.get('sourceDate') is None or frame['sourceDate'] > frame['date'] or
            frame.get('status') not in {'observed','reconstructed','period-assessment','carried-forward'} or
            any(selected.get(k) != source_ref[k] for k in ('id','date','sha256'))):
        raise ValueError('Daily product does not match its published source contract')


def resolved_features(frame, source, snapshots):
    base = source.get('baseGeometry')
    fs = snapshots[base['id']]['features']['features'] if base else source['features']['features']
    if base or frame['status'] == 'carried-forward' or source['date'] != frame['date']:
        # Preserve geometry verbatim (multipart and holes), clear stale activity.
        return [f for f in fs if f['properties']['kind'] in ('perimeter','affected')]
    return fs


def prepare(output, capture_config, scene_manifest):
    if not __debug__:
        raise RuntimeError('Source verification must not run with Python assertions disabled')
    output = Path(output).resolve()
    evidence = []

    def get(path, expected=None):
        p, obj, receipt = fetch(output, path, expected)
        evidence.append(receipt)
        return obj

    cart_path = '/cartography/die-justin/index.json'
    daily_path = '/perimeters/die-justin/index.json'
    index = get(cart_path)
    daily = get(daily_path)
    view = get('/publication/incident/FR-26-00001.json')
    assert index['fireId'] == daily['fireId'] == view['fire_id'] == INCIDENT
    assert index['mapId'] == daily['mapId'] == MAP
    assert index['startDate'] == daily['startDate'] and index['endDate'] == daily['endDate']
    fingerprint = json.dumps([[r['id'], r['sha256']] for r in index['snapshots']], separators=(',', ':')) + '\n'
    assert digest(fingerprint.encode()) == daily['sourceSnapshotsSha256']
    refs = {r['id']: r for r in index['snapshots']}
    assert len(refs) == len(index['snapshots'])

    requests_to_make = [(cart_path.rsplit('/', 1)[0] + '/' + r['path'], r) for r in refs.values()]
    requests_to_make += [(daily_path.rsplit('/', 1)[0] + '/' + r['path'], r) for r in daily['days']]
    requests_to_make += [(daily_path.rsplit('/', 1)[0] + '/' + r['path'], r) for r in daily['naturalFootprints'].values()]
    for key in ('chronology', 'reconciliation'):
        if key in index:
            ref = index[key]
            requests_to_make.append((cart_path.rsplit('/', 1)[0] + '/' + ref['path'], ref))
    assert len(requests_to_make) < 300
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda job: fetch(output, *job), requests_to_make))
    loaded = {p: obj for p, obj, receipt in results}
    evidence.extend(receipt for p, obj, receipt in results)
    snapshots = {key: loaded['/cartography/die-justin/' + ref['path']] for key, ref in refs.items()}
    chronology = loaded['/cartography/die-justin/' + index['chronology']['path']]
    assert chronology['fireId'] == INCIDENT
    # The archive is newest-first; the public record is oldest-first.
    comparable = lambda entries: sorted(json.dumps(e, sort_keys=True, ensure_ascii=True) for e in entries)
    assert comparable(chronology['entries']) == comparable(view['timeline']), 'Published chronology and public record differ'
    chronology_entries = sorted(view['timeline'], key=lambda e: e['occurred_at'])
    for key, item in snapshots.items():
        ref = refs[key]
        assert item['id'] == key and item['date'] == ref['date'] and item['kind'] == ref['kind']
        assert item['features']['type'] == 'FeatureCollection'
        base = item.get('baseGeometry')
        if base:
            source = refs[base['id']]
            assert source['kind'] != 'daily-reconstruction' and source['date'] <= ref['date']
            assert all(source[k] == base[k] for k in ('path', 'sha256', 'bytes'))

    frames = []
    activity_kinds = {'active', 'front', 'flame', 'thermal'}
    first = date.fromisoformat(daily['startDate'])
    for offset, ref in enumerate(daily['days']):
        frame = loaded['/perimeters/die-justin/' + ref['path']]
        assert (date.fromisoformat(frame['date']) - first).days == offset
        assert frame['carryActivityForward'] is False and frame['fireId'] == INCIDENT
        source_ref = refs[frame['snapshot']['id']]
        validate_daily_source(frame, source_ref)
        source = snapshots[source_ref['id']]
        fs = resolved_features(frame, source, snapshots)
        held = frame['status'] == 'carried-forward' or source_ref['date'] != frame['date']
        if held:
            fs = [f for f in fs if f['properties']['kind'] in ('perimeter', 'affected')]
        counts = dict(collections.Counter(f['properties']['kind'] for f in fs))
        assert not held or not (set(counts) & activity_kinds)
        frames.append({
            'calendar_day': frame['date'], 'day_index': offset, 'basis': frame['status'],
            'source_date': frame['sourceDate'], 'snapshot_id': source_ref['id'],
            'snapshot': 'sources/cartography/die-justin/' + source_ref['path'],
            'snapshot_sha256': source_ref['sha256'], 'base_geometry': source.get('baseGeometry'),
            'daily_artifact': 'sources/perimeters/die-justin/' + ref['path'],
            'display_footprint': frame['naturalFootprint'],
            'feature_counts_after_site_resolution': counts,
            'clear_previous_activity': True,
            'activity_allowed_from_this_snapshot': bool(set(counts) & activity_kinds),
            'observation_window': {'from': source['observedFrom'], 'to': source['observedTo']},
            'reconstruction': source.get('reconstruction'),
            'exact_flame_intensity': None, 'weather': None,
        })
    assert frames[-1]['calendar_day'] == daily['endDate']
    for entry in chronology_entries:
        datetime.fromisoformat(entry['occurred_at'].replace('Z', '+00:00'))
        assert entry.get('record_type') != 'publication'
    capture_bytes = Path(capture_config).read_bytes()
    config = json.loads(capture_bytes)
    binding = {'scene_revision':config['scene_revision'],
               'capture_configuration_sha256':digest(capture_bytes),
               'scene_files_manifest_sha256':digest(Path(scene_manifest).read_bytes()),
               'immutable_entry':'scene.usda','capture_entry':'capture_ready.usda',
               'full_scene_restoration_verified':False,
               'geometry_projection_and_coverage':'pending',
               'crs':'EPSG:2154','up_axis':'Z','units':'metres'}
    start = datetime.fromisoformat(config['period']['start']).date()
    end = datetime.fromisoformat(config['period']['end_exclusive']).date()
    simulation_frames = [f for f in frames if start <= date.fromisoformat(f['calendar_day']) < end]
    if len(simulation_frames) != (end-start).days:
        raise ValueError('Published daily products do not cover the entire simulation period')
    source_id = digest(encoded(sorted(evidence, key=lambda r: r['path'])))[:16]
    scenario = {
        'schema': 'fireviewer.incident-replay-inputs.v1', 'id': 'die-justin-' + source_id,
        'incident_id': INCIDENT, 'site': ORIGIN + '/incendie/' + INCIDENT,
        'mode': 'documented_historical_replay', 'map_binding': binding,
        'period': config['period'],
        'source_period': {'from': daily['startDate'], 'to': daily['endDate']},
        'clock': {'calendar_days': len(frames), 'playback_speed': 'operator_controlled',
                  'date_precision_preserved': True, 'date_only_timestamps_are_not_observed_times': True},
        'chronology': chronology_entries, 'daily_frames': frames,
        'simulation_daily_frames': simulation_frames,
        'observation_snapshots': [ref for ref in refs.values() if ref['kind'] != 'daily-reconstruction'],
        'rules': {
            'timeline_and_perimeters': 'published site versions, checksum-bound',
            'source_to_scene': 'EPSG:4326 -> EPSG:2154, subtract map anchor; sample scene terrain for Z',
            'geometry_projection_status': 'pending', 'full_map_coverage_status': 'pending',
            'affected': 'past burned extent; preserve source holes and multipart geometry',
            'perimeter': 'spatial envelope; never ignite its entire interior automatically',
            'display_footprint': 'site display convention, not a per-tree destruction measurement',
            'front_and_flame': 'use only their dated source geometry and observation interval',
            'thermal': 'detection with source footprint/uncertainty; not a measured flame shape',
            'carried_forward': 'retain dated extent; clear prior active/front/flame/thermal layers',
            'between_observations': 'no undocumented interpolation in reference replay',
            'weather_and_intensity': 'use documented parameters when available; overrides marked synthetic',
            'physical_fire_calibrated': False,
        },
        'execution': {'gpu_started': False, 'usd_scenario_authored': False,
                      'live_video_verified': False, 'status': 'published_inputs_verified_pending_scene_adapter'},
        'sources': sorted(evidence, key=lambda r: r['path']),
    }
    qa = {'source_files': len(evidence), 'all_referenced_hashes_and_sizes_verified': True,
          'chronology_entries': len(chronology['entries']), 'chronology_matches_public_record': True,
          'daily_frames': len(frames), 'snapshot_versions': len(refs),
          'simulation_daily_frames':len(simulation_frames),
          'snapshot_kinds': dict(collections.Counter(r['kind'] for r in refs.values())),
          'day_statuses': dict(collections.Counter(f['basis'] for f in frames)),
          'carried_forward_activity_cleared': True, 'date_precision_preserved': True,
          'map_geometry_projection_and_coverage': 'pending', 'render_and_replay': 'not_executed'}
    write(output / 'scenario.json', encoded(scenario))
    write(output / 'input_verification.json', encoded(qa))
    write(output / 'sources_manifest.json', encoded({'origin': ORIGIN, 'files': scenario['sources']}))
    print(json.dumps({'scenario': scenario['id'], **qa}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--capture-config', required=True)
    parser.add_argument('--scene-manifest', required=True)
    args = parser.parse_args()
    prepare(args.output, args.capture_config, args.scene_manifest)

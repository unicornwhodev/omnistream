"""Explicit local pixel budgets; no automatic resolution escalation."""
import json
from pathlib import Path


def load_render_profile(name=None):
    path = Path(__file__).with_name('render_profiles.json')
    catalog = json.loads(path.read_text(encoding='utf-8'))
    name = name or catalog['default']
    if name not in catalog['profiles']:
        raise ValueError('Unknown local render profile; choose hd, full_hd or qhd')
    return name, catalog['profiles'][name]

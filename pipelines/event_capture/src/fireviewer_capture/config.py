"""Configuration validation and a stable run identity, without backend access."""
from pathlib import Path
from datetime import timedelta
import json
import math

from .models import identifier, aware_time, digest, ContractError, simulated_us


def validate_config(value):
    c = json.loads(json.dumps(value, allow_nan=False))
    for key in ["scenario_id", "scene_revision"]: identifier(c[key])
    if type(c["seed"]) is not int or not 0<=c['seed']<=2**32-1: raise ContractError("Seed must be an unsigned 32-bit integer")
    period = c["period"]; start = aware_time(period["start"]); end = aware_time(period["end_exclusive"])
    if end <= start: raise ContractError("Scenario period must be increasing")
    simulated_us((end-start).total_seconds())
    acceleration = c["acceleration"]
    if type(acceleration) not in (int,float) or not math.isfinite(acceleration) or not 250 <= acceleration <= 1000:
        raise ContractError("Requested acceleration must be between 250 and 1000")
    cameras = c["cameras"]; zones = c["zones"]
    if not zones or len(zones)>64 or len({z["id"] for z in zones})!=len(zones):
        raise ContractError("Zone identifiers must be unique and bounded")
    for z in zones: identifier(z["id"])
    if len(cameras)>512 or len({x["id"] for x in cameras})!=len(cameras):
        raise ContractError("Camera identifiers must be unique and bounded")
    paths = set()
    for cam in cameras:
        identifier(cam["id"])
        path = cam["usd_path"]
        if not path.startswith("/World/") or ".." in path or path in paths:
            raise ContractError("Camera USD paths must be unique absolute World paths")
        paths.add(path)
        for key in ["position_m", "look_at_m", "up"]:
            if len(cam[key])!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in cam[key]):
                raise ContractError("Camera pose values must be finite three-vectors")
        if any(type(cam[k]) not in (float,int) or not math.isfinite(cam[k]) or cam[k]<=0 for k in ['focal_length_mm','horizontal_aperture_mm']):
            raise ContractError("Optical design dimensions must be positive")
        import numpy as np
        view=np.subtract(cam['look_at_m'],cam['position_m'])
        if np.linalg.norm(view)<1e-9 or np.linalg.norm(np.cross(view,cam['up']))<1e-9:
            raise ContractError('Camera look direction and up must define a nondegenerate frame')
    mapping = {cam["id"]:cam for cam in cameras}; used = []
    for zone in zones:
        if len(zone["camera_ids"])!=5 or len(set(zone["camera_ids"]))!=5:
            raise ContractError("Each surveillance group requires exactly five fixed cameras")
        if any(i not in mapping for i in zone["camera_ids"]): raise ContractError("Unknown group camera")
        used.extend(zone["camera_ids"])
    if len(set(used))!=len(used) or set(used)!=set(mapping):
        raise ContractError("Each configured camera must belong to exactly one zone")
    render = c["render"]
    if (len(render["resolution_px"])!=2 or
            any(type(x) is not int or not 16<=x<=8192 for x in render["resolution_px"])):
        raise ContractError("Render resolution is outside bounds")
    cap=render["max_active_products"]; cached=render["max_cached_products"]
    if type(cap) is not int or not 1<=cap<=64 or type(cached) is not int or not cap<=cached<=128:
        raise ContractError("Invalid active/cached Render Product limits")
    if type(render["rt_subframes"]) is not int or not 1<=render["rt_subframes"]<=64:
        raise ContractError("RT subframes must be between 1 and 64")
    if render.get("channels") != ["rgb"]:
        raise ContractError("This first qualification supports explicit RGB capture only")
    if type(render.get('seed')) is not int or render['seed']!=c['seed']:
        raise ContractError('Scenario and render seeds must agree')
    if simulated_us(c["activity"]["poll_interval_sim_s"])<=0:
        raise ContractError("Activity polling needs a positive simulated interval")
    from .activity import ZoneActivityTracker
    from .scheduler import CaptureScheduler
    ZoneActivityTracker(zones,c["activity"]); CaptureScheduler([z["id"] for z in zones],c["capture_policy"])
    return c


def load_config(path):
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))


def config_identity(config):
    return digest(validate_config(config))

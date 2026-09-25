"""Dependency-free validation shared by the live scene service and its tests.
No arbitrary Python, USD snippets, file references or extension loading is accepted.
"""
import math
import re

MAX_OPERATIONS = 32
MAX_KEYS = 120
MAX_WATCHES = 16
_PRIM = re.compile(r"^/(?:[A-Za-z_][A-Za-z0-9_]*)(?:/[A-Za-z_][A-Za-z0-9_]*)*$")
ATTRIBUTE_RULES = {
    "physics:mass": ("number", 0.000001, 1e9),
    "physics:density": ("number", 0, 1e9),
    "physics:rigidBodyEnabled": ("bool",),
    "physics:kinematicEnabled": ("bool",),
    "physics:collisionEnabled": ("bool",),
    "physics:velocity": ("vector", -1e6, 1e6),
    "physics:angularVelocity": ("vector", -1e6, 1e6),
    "physics:gravityMagnitude": ("number", 0, 1e6),
    "physics:gravityDirection": ("vector", -1, 1),
    "physics:staticFriction": ("number", 0, 10),
    "physics:dynamicFriction": ("number", 0, 10),
    "physics:restitution": ("number", 0, 1),
}


def number(value, label, minimum=-1e9, maximum=1e9):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if value < minimum or value > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return float(value)


def integer(value, label, minimum, maximum):
    number(value, label, minimum, maximum)
    if int(value) != value:
        raise ValueError(f"{label} must be an integer")
    return int(value)


def boolean(value, label):
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def vector(value, label, minimum=-1e6, maximum=1e6):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must have exactly three components")
    return [number(x, label, minimum, maximum) for x in value]


def prim_path(value, allow_root=False):
    if allow_root and value == "/":
        return value
    if not isinstance(value, str) or len(value) > 512 or not _PRIM.fullmatch(value):
        raise ValueError("primPath must be an absolute, non-root USD prim path (ASCII identifiers)")
    return value


def keys(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        raise ValueError("Unknown or invalid fields")
    if set(required) - set(obj):
        raise ValueError("Missing required fields: " + ", ".join(sorted(set(required) - set(obj))))
    return obj


def text(value, label, max_length=120):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{label} must be non-empty text (max {max_length})")
    return value.strip()


def trs(obj):
    keys(obj, ("translation", "rotation", "scale", "timeSeconds"), ("translation", "rotation", "scale"))
    result = {"translation": vector(obj["translation"], "translation"),
              "rotation": vector(obj["rotation"], "rotation", -36000, 36000),
              "scale": vector(obj["scale"], "scale", 0.0001, 10000)}
    if "timeSeconds" in obj:
        result["timeSeconds"] = number(obj["timeSeconds"], "timeSeconds", 0, 1e6)
    return result


def validate_operations(operations):
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise ValueError(f"operations must contain 1..{MAX_OPERATIONS} items")
    result = []
    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each operation must be an object")
        kind = raw.get("op")
        if kind == "playback_range":
            keys(raw, ("op", "startSeconds", "endSeconds", "framesPerSecond"), ("startSeconds", "endSeconds", "framesPerSecond"))
            start = number(raw["startSeconds"], "startSeconds", 0, 1e6)
            end = number(raw["endSeconds"], "endSeconds", 0, 1e6)
            fps = number(raw["framesPerSecond"], "framesPerSecond", 1, 240)
            if end - start < 1 / fps:
                raise ValueError("Playback range must contain at least one frame")
            result.append({"op": kind, "startSeconds": start, "endSeconds": end, "framesPerSecond": fps})
            continue
        path = prim_path(raw.get("primPath"))
        common = {"op": kind, "primPath": path}
        if kind == "transform":
            keys(raw, ("op", "primPath", "translation", "rotation", "scale"), ("translation", "rotation", "scale"))
            result.append({**common, **trs({k: raw[k] for k in ("translation", "rotation", "scale")})})
        elif kind == "animate_transform":
            keys(raw, ("op", "primPath", "keys"), ("keys",))
            frames = raw["keys"]
            if not isinstance(frames, list) or not 2 <= len(frames) <= MAX_KEYS:
                raise ValueError(f"Animation requires 2..{MAX_KEYS} complete TRS keys")
            frames = [trs(k) for k in frames]
            if any("timeSeconds" not in k for k in frames):
                raise ValueError("Each key requires timeSeconds")
            times = [k["timeSeconds"] for k in frames]
            if any(a >= b for a, b in zip(times, times[1:])):
                raise ValueError("Key times must be strictly increasing")
            result.append({**common, "keys": frames})
        elif kind == "rigid_body":
            keys(raw, ("op", "primPath", "mass", "kinematic", "collider"), ("mass", "kinematic", "collider"))
            result.append({**common, "mass": number(raw["mass"], "mass", 1e-6, 1e9),
                           "kinematic": boolean(raw["kinematic"], "kinematic"),
                           "collider": boolean(raw["collider"], "collider")})
        elif kind == "collider":
            keys(raw, ("op", "primPath", "enabled"), ("enabled",))
            result.append({**common, "enabled": boolean(raw["enabled"], "enabled")})
        elif kind == "physics_scene":
            keys(raw, ("op", "primPath", "gravityDirection", "gravityMagnitude"), ("gravityDirection", "gravityMagnitude"))
            direction = vector(raw["gravityDirection"], "gravityDirection", -1, 1)
            if sum(x*x for x in direction) < 1e-12:
                raise ValueError("gravityDirection cannot be zero")
            norm = math.sqrt(sum(x*x for x in direction))
            result.append({**common, "gravityDirection": [x/norm for x in direction],
                           "gravityMagnitude": number(raw["gravityMagnitude"], "gravityMagnitude", 0, 1e6)})
        elif kind == "attribute":
            keys(raw, ("op", "primPath", "attribute", "value"), ("attribute", "value"))
            name = raw["attribute"]
            rule = ATTRIBUTE_RULES.get(name) if isinstance(name, str) else None
            if not rule:
                raise ValueError("Only allowlisted physical attributes can be edited")
            value = raw["value"]
            if rule[0] == "bool":
                value = boolean(value, name)
            elif rule[0] == "vector":
                value = vector(value, name, *rule[1:])
            else:
                value = number(value, name, *rule[1:])
            if name == "physics:gravityDirection" and sum(x*x for x in value) < 1e-12:
                raise ValueError("gravityDirection cannot be zero")
            result.append({**common, "attribute": name, "value": value})
        else:
            raise ValueError(f"Unsupported operation: {kind}")
    return result


def validate_watches(values):
    if not isinstance(values, list) or len(values) > MAX_WATCHES:
        raise ValueError(f"At most {MAX_WATCHES} attribute watches are allowed")
    result = []
    for item in values:
        keys(item, ("primPath", "attribute"), ("primPath", "attribute"))
        name = text(item["attribute"], "attribute", 120)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_:]*", name):
            raise ValueError("Invalid attribute name")
        pair = {"primPath": prim_path(item["primPath"]), "attribute": name}
        if pair not in result:
            result.append(pair)
    return result

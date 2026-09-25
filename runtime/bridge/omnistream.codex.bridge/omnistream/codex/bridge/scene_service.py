"""Bounded, transactional authoring of the CURRENT Kit stage.

All calls run on Kit's main loop. Preview authors an isolated USD stage, never
live data. Apply transfers an already validated layer in one synchronous call.
Only this managed override layer can be undone/exported; no source layer Save.
"""
import hashlib
import itertools
import json
import math
import os
import pathlib
import time
import uuid
from collections import deque

from pxr import Gf, Sdf, Tf, Usd, UsdGeom, UsdPhysics
from .scene_policy import (ATTRIBUTE_RULES, integer, number, prim_path,
                           text, validate_operations, validate_watches)


def json_value(value, depth=0):
    """Do not materialize unbounded arrays or return non-JSON NaN/Inf."""
    if value is None or isinstance(value, (bool, str)):
        return value[:512] if isinstance(value, str) else value
    if isinstance(value, (float, int)):
        return value if math.isfinite(value) else {"nonFinite": str(value)}
    if depth >= 3:
        return str(value)[:160]
    try:
        length = len(value)
        if length > 32:
            return {"length": length, "truncated": True}
        return [json_value(v, depth + 1) for v in value]
    except (TypeError, AttributeError):
        return str(value)[:160]


def contains_nonfinite(value):
    if isinstance(value, dict):
        return "nonFinite" in value or any(contains_nonfinite(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_nonfinite(v) for v in value)
    return False


class SceneService:
    def __init__(self, stage_provider, timeline_provider, workspace_root, emit, physx_available=lambda: False):
        self._get_stage = stage_provider
        self._get_timeline = timeline_provider
        self._workspace = pathlib.Path(workspace_root).resolve()
        self._emit = emit
        self._physx_available = physx_available
        self._stage = None
        self._layer = None
        self._notice = None
        self._own_write = False
        self._revision = 0
        self._stage_id = None
        self._previews = {}
        self._undo = deque(maxlen=12)
        self._watches = []
        self._pause_nonfinite = True
        self._run = None
        self._metadata_baseline = None
        self._metadata_owned = None

    def close(self):
        if self._notice:
            self._notice.Revoke()
        self._notice = None

    def _changed(self, notice, sender):
        if not self._own_write:
            self._revision += 1
            self._previews.clear()

    def _ensure(self):
        stage = self._get_stage()
        if not stage:
            raise RuntimeError("stage_not_open: Open a USD stage in the managed Kit runtime first")
        if stage != self._stage:
            self.close()
            self._stage = stage
            self._stage_id = uuid.uuid4().hex
            self._revision = 0
            self._layer = Sdf.Layer.CreateAnonymous("omnistream-overrides.usda")
            self._previews.clear()
            self._undo.clear()
            self._watches = []
            self._run = None
            self._metadata_baseline = None
            self._metadata_owned = None
            self._notice = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._changed, stage)
            self._emit("stage_changed", {"stageId": self._stage_id})
        return stage

    def identity(self):
        self._ensure()
        return {"stageId": self._stage_id, "revision": self._revision,
                "hasSessionEdits": not self._layer.empty,
                "undoDepth": len(self._undo)}

    def _expected(self, params, revision=True):
        self._ensure()
        if params.get("stageId") != self._stage_id:
            raise ValueError("stage_changed: Inspect the current scene again; this stageId is no longer valid")
        if revision and params.get("expectedRevision") != self._revision:
            raise ValueError("revision_conflict: The scene changed. Inspect and preview again")

    def _editable(self, physics=False):
        stage = self._ensure()
        root = stage.GetRootLayer()
        if not root.anonymous:
            source = pathlib.Path(root.realPath or root.identifier).resolve(strict=True)
            try:
                source.relative_to(self._workspace)
            except ValueError as exc:
                raise ValueError("workspace_boundary: The current stage is outside the authorized workspace") from exc
        timeline = self._get_timeline()
        if timeline.is_playing():
            raise RuntimeError("pause_required: Pause playback before previewing/applying scene corrections")
        if physics and not timeline.is_stopped():
            raise RuntimeError("stop_required: Stop physics before changing bodies, colliders or undoing edits")

    def _prim(self, stage, path, editable=False):
        prim_path(path)
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsActive() or not prim.IsLoaded():
            raise ValueError("prim_unavailable: Prim is missing, inactive or unloaded: " + path)
        if editable and (prim.IsInstance() or prim.IsInstanceProxy() or prim.IsInPrototype()):
            raise ValueError("instance_read_only: Edit the source instance explicitly outside this tool")
        return prim

    def inspect(self, params):
        stage = self._ensure()
        if params.get("stageId"):
            self._expected(params, revision=False)
        parent = params.get("parentPath", "/")
        prim_path(parent, allow_root=True)
        node = stage.GetPseudoRoot() if parent == "/" else self._prim(stage, parent)
        offset = integer(params.get("offset", 0), "offset", 0, 1_000_000)
        limit = integer(params.get("limit", 60), "limit", 1, 100)
        children = list(itertools.islice(iter(node.GetChildren()), offset, offset + limit + 1))
        rows = []
        for p in children[:limit]:
            rows.append({"path": str(p.GetPath()), "name": p.GetName(), "type": p.GetTypeName(),
                         "hasChildren": bool(p.GetChildren()), "rigidBody": p.HasAPI(UsdPhysics.RigidBodyAPI),
                         "collider": p.HasAPI(UsdPhysics.CollisionAPI),
                         "instance": p.IsInstance() or p.IsInstanceProxy()})
        root = stage.GetRootLayer()
        try:
            writable_scope = root.anonymous or pathlib.Path(root.realPath or root.identifier).resolve(strict=True).is_relative_to(self._workspace)
        except (ValueError, OSError):
            writable_scope = False
        return {**self.identity(), "stagePath": stage.GetRootLayer().realPath or stage.GetRootLayer().identifier,
                "parentPath": parent, "prims": rows, "nextOffset": offset + limit if len(children) > limit else None,
                "metersPerUnit": UsdGeom.GetStageMetersPerUnit(stage), "upAxis": str(UsdGeom.GetStageUpAxis(stage)),
                "timeCodesPerSecond": stage.GetTimeCodesPerSecond(),
                "startSeconds": stage.GetStartTimeCode() / stage.GetTimeCodesPerSecond(),
                "endSeconds": stage.GetEndTimeCode() / stage.GetTimeCodesPerSecond(),
                "capabilities": {"authoring": writable_scope, "transformAnimation": True,
                                 "rigidBodySimulation": bool(self._physx_available()),
                                 "arbitraryPython": False, "sourceOverwrite": False,
                                 "telemetryHz": 4, "maxWatchAttributes": 16}}

    def inspect_prim(self, params):
        self._expected(params, False)
        prim = self._prim(self._stage, params.get("primPath"))
        tc = self._get_timeline().get_current_time() * self._stage.GetTimeCodesPerSecond()
        attrs = []
        for attr in itertools.islice(iter(prim.GetAttributes()), 80):
            count = attr.GetNumTimeSamples()
            attrs.append({"name": attr.GetName(), "type": str(attr.GetTypeName()),
                          "value": {"arrayOmitted": True} if attr.GetTypeName().isArray else json_value(attr.Get(Usd.TimeCode(tc))),
                          "timeSampleCount": count,
                          "editable": attr.GetName() in ATTRIBUTE_RULES})
        xform = UsdGeom.Xformable(prim)
        matrix = xform.GetLocalTransformation(Usd.TimeCode(tc)) if xform else None
        if isinstance(matrix, tuple):
            matrix = matrix[0]
        editable_trs = None
        if xform:
            ordered = xform.GetOrderedXformOps()
            allowed = (UsdGeom.XformOp.TypeTranslate, UsdGeom.XformOp.TypeRotateXYZ, UsdGeom.XformOp.TypeScale)
            types = [op.GetOpType() for op in ordered]
            if all(t in allowed for t in types) and len(set(types)) == len(types) and types == sorted(types, key=allowed.index) and not any(op.IsInverseOp() for op in ordered):
                editable_trs = {"translation": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]}
                names = dict(zip(allowed, ("translation", "rotation", "scale")))
                for op in ordered:
                    value = op.Get(Usd.TimeCode(tc))
                    if value is None:
                        editable_trs = None
                        break
                    editable_trs[names[op.GetOpType()]] = json_value(value)
        return {**self.identity(), "primPath": str(prim.GetPath()), "editableTrs": editable_trs, "type": prim.GetTypeName(),
                "schemas": list(prim.GetAppliedSchemas()), "attributes": attrs,
                "attributeLimit": 80, "localMatrix": json_value(matrix) if matrix is not None else None,
                "transformConvention": "local TRS, XYZ Euler degrees; replaces this prim's composed xformOpOrder"}

    @staticmethod
    def _physics_ops(ops):
        return any(o["op"] in ("physics_scene", "rigid_body", "collider", "attribute") for o in ops)

    def _author(self, stage, layer, ops):
        with Usd.EditContext(stage, layer):
            for op in ops:
                kind = op["op"]
                if kind == "playback_range":
                    layer.customLayerData = {**dict(layer.customLayerData), "omnistreamPlayback": dict(op)}
                    # Stage metadata belongs to root/session, NOT an arbitrary sublayer.
                    with Usd.EditContext(stage, stage.GetSessionLayer()):
                        stage.SetTimeCodesPerSecond(op["framesPerSecond"])
                        stage.SetFramesPerSecond(op["framesPerSecond"])
                        stage.SetStartTimeCode(op["startSeconds"] * op["framesPerSecond"])
                        stage.SetEndTimeCode(op["endSeconds"] * op["framesPerSecond"])
                    continue
                path = op["primPath"]
                if kind == "physics_scene":
                    existing = stage.GetPrimAtPath(path)
                    if existing and not existing.IsA(UsdPhysics.Scene):
                        raise ValueError("physics_scene would replace an existing non-PhysicsScene prim")
                    if existing:
                        self._prim(stage, path, True)
                    else:
                        parent = str(Sdf.Path(path).GetParentPath())
                        if parent != "/":
                            self._prim(stage, parent, True)
                    scene = UsdPhysics.Scene.Define(stage, path)
                    scene.CreateGravityDirectionAttr(Gf.Vec3f(*op["gravityDirection"]))
                    scene.CreateGravityMagnitudeAttr(op["gravityMagnitude"])
                    continue
                prim = self._prim(stage, path, True)
                if kind in ("transform", "animate_transform"):
                    xform = UsdGeom.Xformable(prim)
                    if not xform or prim.IsA(UsdGeom.Camera):
                        raise ValueError("Transform target must be a non-camera Xformable; use dedicated camera tools")
                    body = UsdPhysics.RigidBodyAPI(prim)
                    if kind == "animate_transform" and body and not body.GetKinematicEnabledAttr().Get():
                        raise ValueError("dynamic_animation_conflict: Make this body kinematic before keyframing it")
                    reset = xform.GetResetXformStack()
                    xform.ClearXformOpOrder()
                    specs = (("translate", Sdf.ValueTypeNames.Double3),
                             ("rotateXYZ", Sdf.ValueTypeNames.Float3), ("scale", Sdf.ValueTypeNames.Float3))
                    attrs = [prim.CreateAttribute(f"xformOp:{name}:omnistream", typ) for name, typ in specs]
                    for attr in attrs:
                        attr.Clear()  # Only clears the trial/managed layer's samples.
                    xform.SetXformOpOrder([UsdGeom.XformOp(a) for a in attrs], reset)
                    frames = op["keys"] if kind == "animate_transform" else [op]
                    for frame in frames:
                        tc = Usd.TimeCode(frame["timeSeconds"] * stage.GetTimeCodesPerSecond()) if kind == "animate_transform" else Usd.TimeCode.Default()
                        attrs[0].Set(Gf.Vec3d(*frame["translation"]), tc)
                        attrs[1].Set(Gf.Vec3f(*frame["rotation"]), tc)
                        attrs[2].Set(Gf.Vec3f(*frame["scale"]), tc)
                elif kind == "rigid_body":
                    if not UsdGeom.Xformable(prim):
                        raise ValueError("Rigid bodies must be Xformable")
                    ancestor = prim.GetParent()
                    while ancestor and not ancestor.IsPseudoRoot():
                        if ancestor.HasAPI(UsdPhysics.RigidBodyAPI):
                            raise ValueError("nested_rigid_body: Nested bodies require an explicit specialist setup")
                        ancestor = ancestor.GetParent()
                    body = UsdPhysics.RigidBodyAPI.Apply(prim)
                    body.CreateRigidBodyEnabledAttr(True)
                    body.CreateKinematicEnabledAttr(op["kinematic"])
                    UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(op["mass"])
                    if op["collider"]:
                        self._collider(prim, True)
                    elif prim.HasAPI(UsdPhysics.CollisionAPI):
                        UsdPhysics.CollisionAPI(prim).CreateCollisionEnabledAttr(False)
                elif kind == "collider":
                    self._collider(prim, op["enabled"])
                elif kind == "attribute":
                    attr = prim.GetAttribute(op["attribute"])
                    if not attr:
                        raise ValueError("Attribute is absent; apply its physics schema first")
                    value = op["value"]
                    typ = str(attr.GetTypeName())
                    if isinstance(value, list):
                        if typ not in ("float3", "double3", "vector3f", "vector3d"):
                            raise ValueError("Attribute type is not a supported 3D vector")
                        value = Gf.Vec3d(*value) if typ in ("double3", "vector3d") else Gf.Vec3f(*value)
                    elif isinstance(value, bool):
                        if typ != "bool":
                            raise ValueError("Attribute type is not boolean")
                    elif typ not in ("float", "double"):
                        raise ValueError("Attribute type is not float/double")
                    if not attr.Set(value):
                        raise RuntimeError("USD attribute authoring failed")

    @staticmethod
    def _collider(prim, enabled):
        if not UsdGeom.Gprim(prim):
            raise ValueError("Collider target must be a geometry prim, not a grouping Xform")
        UsdPhysics.CollisionAPI.Apply(prim).CreateCollisionEnabledAttr(enabled)
        if prim.IsA(UsdGeom.Mesh):
            UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr("convexHull")

    def preview(self, params):
        self._expected(params)
        ops = validate_operations(params.get("operations"))
        self._editable(self._physics_ops(ops))
        label = text(params.get("label", "Scene correction"), "label", 120)
        candidate = Sdf.Layer.CreateAnonymous("omnistream-preview.usda")
        candidate.TransferContent(self._layer)
        session = Sdf.Layer.CreateAnonymous("omnistream-preview-session.usda")
        session.TransferContent(self._stage.GetSessionLayer())
        session.subLayerPaths = [candidate.identifier] + [p for p in session.subLayerPaths if p != self._layer.identifier]
        trial = Usd.Stage.Open(self._stage.GetRootLayer(), session, load=Usd.Stage.LoadNone)
        trial.SetLoadRules(self._stage.GetLoadRules())
        self._author(trial, candidate, ops)
        for authored_path in {op.get("primPath") for op in ops if op.get("primPath")}:
            authored_prim = trial.GetPrimAtPath(authored_path)
            spec = candidate.GetPrimAtPath(authored_prim.GetPath())
            if not spec:
                continue
            for name in spec.attributes.keys():
                attr = authored_prim.GetAttribute(name)
                stack = attr.GetPropertyStack() if attr else []
                if stack and stack[0].layer == session:
                    raise ValueError("session_opinion_conflict: An existing session opinion masks the proposed property: " + str(attr.GetPath()))
        serialized = candidate.ExportToString()
        if len(serialized.encode("utf8")) > 2 * 1024 * 1024:
            raise ValueError("Managed edits exceed the 2 MiB session limit")
        preview_id = uuid.uuid4().hex
        self._previews = {k: v for k, v in self._previews.items() if v["expires"] > time.monotonic()}
        if len(self._previews) >= 4:
            self._previews.pop(next(iter(self._previews)))
        self._previews[preview_id] = {"text": serialized, "revision": self._revision,
                                      "expires": time.monotonic() + 120, "ops": ops, "label": label}
        warnings = []
        if any(o["op"] in ("transform", "animate_transform") for o in ops):
            warnings.append("Local TRS replaces the target's transform stack in the override layer; source data is preserved.")
        if self._physics_ops(ops) and not self._physx_available():
            warnings.append("PhysX is not enabled: USD can be configured, but physical execution is unavailable.")
        return {**self.identity(), "previewId": preview_id, "expiresInSeconds": 120,
                "label": label, "operationCount": len(ops), "operations": ops,
                "warnings": warnings, "persistence": "session-only", "sourceModified": False}

    def _sync_playback_metadata(self):
        session = self._stage.GetSessionLayer()
        props = {"StartTimeCode": "startTimeCode", "EndTimeCode": "endTimeCode",
                 "TimeCodesPerSecond": "timeCodesPerSecond", "FramesPerSecond": "framesPerSecond"}
        config = self._layer.customLayerData.get("omnistreamPlayback")
        if self._metadata_owned is not None:
            for prop, expected in self._metadata_owned.items():
                if getattr(session, prop) != expected:
                    raise RuntimeError("metadata_conflict: Timeline metadata was edited externally; export corrections and reconcile the session before undo/apply")
        if config:
            if self._metadata_baseline is None:
                self._metadata_baseline = {method: (getattr(session, prop) if getattr(session, "Has"+method)() else None)
                                           for method, prop in props.items()}
            session.timeCodesPerSecond = config["framesPerSecond"]
            session.framesPerSecond = config["framesPerSecond"]
            session.startTimeCode = config["startSeconds"] * config["framesPerSecond"]
            session.endTimeCode = config["endSeconds"] * config["framesPerSecond"]
            self._metadata_owned = {prop: getattr(session, prop) for prop in props.values()}
        elif self._metadata_baseline is not None:
            for method, value in self._metadata_baseline.items():
                if value is None:
                    getattr(session, "Clear" + method)()
                else:
                    setattr(session, props[method], value)
            self._metadata_baseline = None
            self._metadata_owned = None

    def _transfer(self, value):
        # Sdf.ChangeBlock batches notices; it is NOT a database transaction.
        # Snapshot both affected layers and roll them back on authoring failure.
        candidate = Sdf.Layer.CreateAnonymous("omnistream-restore.usda")
        if not candidate.ImportFromString(value):
            raise RuntimeError("Invalid managed layer snapshot")
        session = self._stage.GetSessionLayer()
        before_layer = Sdf.Layer.CreateAnonymous("before-managed.usda")
        before_layer.TransferContent(self._layer)
        before_session = Sdf.Layer.CreateAnonymous("before-session.usda")
        before_session.TransferContent(session)
        before_metadata = self._metadata_baseline.copy() if self._metadata_baseline is not None else None
        before_owned = self._metadata_owned.copy() if self._metadata_owned is not None else None
        self._own_write = True
        try:
            try:
                with Sdf.ChangeBlock():
                    self._layer.TransferContent(candidate)
                    if self._layer.identifier not in session.subLayerPaths:
                        session.subLayerPaths = [self._layer.identifier] + list(session.subLayerPaths)
                    self._sync_playback_metadata()
            except Exception:
                with Sdf.ChangeBlock():
                    self._layer.TransferContent(before_layer)
                    session.TransferContent(before_session)
                self._metadata_baseline = before_metadata
                self._metadata_owned = before_owned
                raise
        finally:
            self._own_write = False
        self._revision += 1
        self._previews.clear()

    def apply(self, params):
        self._expected(params)
        preview = self._previews.get(params.get("previewId"))
        if not preview or preview["expires"] < time.monotonic() or preview["revision"] != self._revision:
            raise ValueError("preview_expired: Create a new preview before applying")
        self._editable(self._physics_ops(preview["ops"]))
        previous = self._layer.ExportToString()
        self._transfer(preview["text"])
        self._undo.append(previous)
        self._emit("patch_applied", {"label": preview["label"], "revision": self._revision,
                                      "operationCount": len(preview["ops"])})
        return {**self.identity(), "applied": True, "label": preview["label"], "sourceModified": False}

    def undo(self, params):
        self._expected(params)
        self._editable(True)
        if not self._undo:
            raise ValueError("undo_empty: No managed correction to undo")
        previous = self._undo[-1]
        self._transfer(previous)
        self._undo.pop()
        self._emit("patch_undone", {"revision": self._revision})
        return {**self.identity(), "undone": True}

    def discard(self, params):
        self._expected(params)
        self._editable(True)
        if params.get("confirm") is not True:
            raise ValueError("Explicit confirmation is required")
        empty = Sdf.Layer.CreateAnonymous("empty.usda")
        self._transfer(empty.ExportToString())
        self._undo.clear()
        self._emit("patch_discarded", {"revision": self._revision})
        return {**self.identity(), "discarded": True}

    def export(self, params):
        self._expected(params)
        self._editable()
        if params.get("confirm") is not True:
            raise ValueError("Explicit export confirmation is required")
        relative = pathlib.Path(text(params.get("relativePath"), "relativePath", 512))
        if relative.is_absolute() or relative.suffix.lower() != ".usda" or ".." in relative.parts or ":" in str(relative):
            raise ValueError("Export must be a new relative .usda path inside the workspace")
        target = self._workspace / relative
        parent = target.parent.resolve(strict=True)
        try:
            parent.relative_to(self._workspace)
        except ValueError as exc:
            raise ValueError("Export path escapes the workspace") from exc
        target = parent / target.name
        export_layer = Sdf.Layer.CreateAnonymous("omnistream-export.usda")
        export_layer.TransferContent(self._layer)
        config = export_layer.customLayerData.get("omnistreamPlayback")
        if config:
            export_layer.startTimeCode = config["startSeconds"] * config["framesPerSecond"]
            export_layer.endTimeCode = config["endSeconds"] * config["framesPerSecond"]
            export_layer.timeCodesPerSecond = config["framesPerSecond"]
            export_layer.framesPerSecond = config["framesPerSecond"]
        data = export_layer.ExportToString().encode("utf8")
        # O_EXCL also rejects existing symlinks. Do not ever overwrite source USD.
        fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        self._emit("patch_exported", {"file": target.name})
        return {**self.identity(), "exported": str(target), "sha256": hashlib.sha256(data).hexdigest(),
                "kind": "override-layer", "standaloneScene": False, "sourceModified": False}

    def watch(self, params):
        self._expected(params, False)
        watches = validate_watches(params.get("properties", []))
        for item in watches:
            prim = self._prim(self._stage, item["primPath"])
            attr = prim.GetAttribute(item["attribute"])
            if attr and attr.GetTypeName().isArray:
                raise ValueError("Array watches are not supported; use scalar/vector attributes")
            if not attr:
                raise ValueError("Watch attribute does not exist: " + item["attribute"])
        pause = params.get("pauseOnNonFinite", True)
        if not isinstance(pause, bool):
            raise ValueError("pauseOnNonFinite must be boolean")
        self._watches = watches
        self._pause_nonfinite = pause
        return {**self.identity(), "properties": watches, "pauseOnNonFinite": pause}

    def sample(self):
        self._ensure()
        timeline = self._get_timeline()
        tc = timeline.get_current_time() * self._stage.GetTimeCodesPerSecond()
        values = []
        for watch in self._watches:
            prim = self._stage.GetPrimAtPath(watch["primPath"])
            attr = prim.GetAttribute(watch["attribute"]) if prim else None
            value = json_value(attr.Get(Usd.TimeCode(tc))) if attr else None
            values.append({**watch, "value": value, "available": bool(attr)})
        if self._pause_nonfinite and timeline.is_playing() and any(contains_nonfinite(v["value"]) for v in values):
            timeline.pause()
            timeline.commit()
            self._emit("guard_paused", {"reason": "non_finite_watch"})
        if self._run:
            if time.monotonic() >= self._run["deadline"]:
                if timeline.is_playing():
                    timeline.pause()
                    timeline.commit()
                self._run["state"] = "wall_limit_reached"
                if not self._run.get("limitEventSent"):
                    self._emit("guard_paused", {"reason": "wall_time_limit", "runId": self._run["runId"]})
                    self._run["limitEventSent"] = True
            else:
                self._run["state"] = "active" if timeline.is_playing() else "paused_or_completed"
        run = {k: v for k, v in self._run.items() if k != "deadline"} if self._run else None
        return {**self.identity(), "timeSeconds": float(timeline.get_current_time()),
                "playing": bool(timeline.is_playing()), "watches": values, "run": run}

    def run(self, params):
        self._expected(params, False)
        timeline = self._get_timeline()
        if timeline.is_playing():
            raise ValueError("already_playing: Pause before starting another bounded run")
        mode = params.get("mode")
        if mode not in ("animation", "physics"):
            raise ValueError("mode must be animation or physics")
        duration = number(params.get("wallTimeLimitSeconds", 60), "wallTimeLimitSeconds", 1, 3600)
        diagnostics = self.diagnose({"stageId": self._stage_id, "maxPrims": 3000})
        if diagnostics["scanCapped"]:
            raise ValueError("diagnostic_incomplete: The bounded structural scan did not finish. Review the whole stage before using an automatic bounded run")
        if mode == "physics":
            if not self._physx_available():
                raise RuntimeError("physics_unavailable: Enable omni.physx in this Kit application and restart")
            if not diagnostics["counts"]["physicsScenes"] or not diagnostics["counts"]["rigidBodies"]:
                raise ValueError("physics_setup_missing: A PhysicsScene and enabled rigid body are required")
        blocking = [issue for issue in diagnostics["issues"] if issue["severity"] == "error"]
        if blocking:
            raise ValueError("scene_diagnostics_failed: " + ", ".join(issue["code"] for issue in blocking[:6]))
        reset = params.get("resetToStart", True)
        if not isinstance(reset, bool):
            raise ValueError("resetToStart must be boolean")
        if reset:
            timeline.stop()
            timeline.commit()
            timeline.set_current_time(timeline.get_start_time())
        timeline.set_looping(False)
        timeline.play()
        timeline.commit()
        self._run = {"runId": uuid.uuid4().hex, "mode": mode, "state": "active",
                     "wallTimeLimitSeconds": duration, "startedAtUnixMs": round(time.time()*1000),
                     "deadline": time.monotonic() + duration}
        self._emit("run_started", {"runId": self._run["runId"], "mode": mode})
        return self.sample()

    def diagnose(self, params):
        self._expected(params, False)
        limit = integer(params.get("maxPrims", 1000), "maxPrims", 1, 5000)
        counts = {"prims": 0, "physicsScenes": 0, "rigidBodies": 0, "colliders": 0, "animatedPrims": 0}
        issues = []
        capped = False
        for index, prim in enumerate(self._stage.Traverse()):
            if index >= limit:
                capped = True
                break
            counts["prims"] += 1
            path = str(prim.GetPath())
            if prim.IsA(UsdPhysics.Scene):
                counts["physicsScenes"] += 1
            body = UsdPhysics.RigidBodyAPI(prim)
            collision = UsdPhysics.CollisionAPI(prim)
            animated = bool(UsdGeom.Xformable(prim) and UsdGeom.Xformable(prim).TransformMightBeTimeVarying())
            counts["animatedPrims"] += int(animated)
            counts["colliders"] += int(bool(collision and collision.GetCollisionEnabledAttr().Get()))
            if body and body.GetRigidBodyEnabledAttr().Get():
                counts["rigidBodies"] += 1
                if animated and not body.GetKinematicEnabledAttr().Get():
                    issues.append({"code": "dynamic_animation_conflict", "severity": "error", "primPath": path,
                                   "message": "A dynamic body has authored transform animation. Decide between dynamics and kinematic animation."})
                mass = UsdPhysics.MassAPI(prim).GetMassAttr().Get() if prim.HasAPI(UsdPhysics.MassAPI) else None
                if mass is not None and (not math.isfinite(mass) or mass < 0):
                    issues.append({"code": "invalid_mass", "severity": "error", "primPath": path, "message": "Mass is invalid."})
            if len(issues) >= 100:
                capped = True
                break
        if not self._physx_available():
            issues.append({"code": "physx_unavailable", "severity": "warning", "message": "Physical execution unavailable in this Kit runtime; USD animation remains available."})
        if counts["rigidBodies"] and not counts["physicsScenes"] and not capped:
            issues.append({"code": "missing_physics_scene", "severity": "error", "message": "No PhysicsScene found within the inspected scope."})
        if capped:
            issues.append({"code": "scan_incomplete", "severity": "warning", "message": "The structural scan reached its limit; absence of a physics scene or other object is not established."})
        if counts["physicsScenes"] > 1:
            issues.append({"code": "multiple_physics_scenes", "severity": "warning", "message": "Multiple physics scenes: verify simulation owner relationships manually."})
        return {**self.identity(), "counts": counts, "issues": issues, "scanCapped": capped,
                "maxPrims": limit, "physicsRuntimeAvailable": bool(self._physx_available()),
                "scope": "USD structure only; not a proof of solver convergence, collision correctness or GPU performance"}

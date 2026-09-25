import asyncio
import json
import os
import pathlib
import socket
import threading
import time
import concurrent.futures

import carb
import omni.ext
import omni.kit.app
import omni.timeline
import omni.usd
from omni.kit.viewport.utility import get_active_viewport
from pxr import Gf, Sdf, Usd, UsdGeom
from .scene_service import SceneService
from .telemetry import TelemetryBuffer, sanitize

_PROTOCOL = 1
_MAX_LINE_BYTES = 64 * 1024
_ALLOWED_USD = {".usd", ".usda", ".usdc", ".usdz"}
_SETTINGS = "/exts/omnistream_codex_bridge"


def _setting(name, default=None):
    value = carb.settings.get_settings().get(f"{_SETTINGS}/{name}")
    return default if value in (None, "") else value


def _safe_message(value):
    return sanitize(value or "Command failed.").strip()[:320]


class OmniStreamCodexBridgeExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._ext_id = ext_id
        self._loop = asyncio.get_event_loop()
        self._stop = threading.Event()
        self._socket = None
        self._thread = None
        self._selected_camera = None
        self._camera_dirty = False
        self._rate_multiplier = 1.0
        self._base_target_fps = None
        self._initial_time_seconds = 0.0
        self._allowed_root = self._normalize_root(_setting("allowedRoot", ""))
        self._host = str(_setting("controlHost", "127.0.0.1"))
        self._port = int(_setting("controlPort", 0) or 0)
        token = os.environ.get("CODEX_OMNIVERSE_CONTROL_TOKEN", "")
        if self._host != "127.0.0.1" or not self._port or len(token) < 32 or not self._allowed_root:
            carb.log_error("OmniStream bridge disabled: invalid loopback control settings or allowedRoot.")
            return
        self._token = token
        self._telemetry = TelemetryBuffer()
        self._scene_service = SceneService(
            lambda: omni.usd.get_context().get_stage(), self._timeline,
            self._allowed_root, self._telemetry.emit, self._physics_available)
        self._sample_at = 0.0
        self._previous_update = None
        self._update_ms = 0.0
        self._update_sub = None
        self._logger = None
        self._telemetry_error_at = 0.0
        self._quiescing = False
        app = omni.kit.app.get_app()
        try:
            from carb import eventdispatcher
            self._update_sub = eventdispatcher.get_eventdispatcher().observe_event(
                observer_name="omnistream/live", event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
                on_event=self._on_update)
        except (ImportError, AttributeError):
            self._update_sub = app.get_update_event_stream().create_subscription_to_pop(
                self._on_update, name="OmniStream live telemetry")
        try:
            self._logger = carb.logging.acquire_logging().add_logger(self._on_log)
        except Exception:
            carb.log_warn("OmniStream Carbonite log callback unavailable; file log tail remains available.")
        self._thread = threading.Thread(target=self._worker, name="omnistream-codex-bridge", daemon=True)
        self._thread.start()
        carb.log_info("OmniStream Codex control bridge starting on authenticated loopback channel.")

    def on_shutdown(self):
        self._update_sub = None
        if getattr(self, "_scene_service", None):
            self._scene_service.close()
        if getattr(self, "_logger", None):
            try:
                carb.logging.acquire_logging().remove_logger(self._logger)
            except Exception:
                pass
            self._logger = None
        self._stop.set()
        sock = self._socket
        self._socket = None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.5)

    def _normalize_root(self, value):
        if not value:
            return None
        try:
            return pathlib.Path(str(value)).expanduser().resolve(strict=True)
        except Exception:
            return None

    def _validated_stage(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("stage path is required")
        candidate = pathlib.Path(value.strip())
        if not candidate.is_absolute():
            candidate = self._allowed_root / candidate
        resolved = candidate.expanduser().resolve(strict=True)
        if resolved.suffix.lower() not in _ALLOWED_USD or not resolved.is_file():
            raise ValueError("stage path must be an existing USD file")
        try:
            resolved.relative_to(self._allowed_root)
        except ValueError as exc:
            raise ValueError("stage path must remain below the allowed workspace root") from exc
        return resolved

    def _worker(self):
        backoff = 0.25
        while not self._stop.is_set():
            try:
                with socket.create_connection((self._host, self._port), timeout=2.0) as sock:
                    self._socket = sock
                    sock.settimeout(0.1)
                    self._send(sock, {"type": "hello", "protocol": _PROTOCOL, "token": self._token})
                    hello = self._read_line(sock)
                    if not hello or hello.get("type") != "hello" or hello.get("ok") is not True:
                        raise RuntimeError("control handshake rejected")
                    backoff = 0.25
                    while not self._stop.is_set():
                        self._flush_events(sock)
                        request = self._read_line(sock)
                        if request is None:
                            continue
                        if request.get("type") != "request" or not isinstance(request.get("id"), str):
                            raise RuntimeError("invalid control request")
                        future = asyncio.run_coroutine_threadsafe(
                            self._dispatch(str(request.get("method", "")), request.get("params") or {}),
                            self._loop,
                        )
                        try:
                            deadline = time.monotonic() + 175.0
                            while True:
                                try:
                                    result = future.result(timeout=0.1)
                                    break
                                except concurrent.futures.TimeoutError:
                                    if future.done():
                                        raise  # A real command exception, not the polling timeout.
                                    self._flush_events(sock)
                                    if self._stop.is_set() or time.monotonic() >= deadline:
                                        # Do not admit another mutation after an unknown outcome.
                                        self._quiescing = True
                                        raise RuntimeError("operation_uncertain: runtime must be safely restarted")
                            self._send(sock, {"type": "response", "id": request["id"], "ok": True, "result": result})
                        except Exception as exc:
                            self._send(sock, {
                                "type": "response",
                                "id": request["id"],
                                "ok": False,
                                "error": {"code": "command_failed", "message": _safe_message(exc)},
                            })
            except (OSError, RuntimeError):
                self._socket = None
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 1.6, 2.0)
            finally:
                self._socket = None

    def _send(self, sock, payload):
        raw = (json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        if len(raw) > _MAX_LINE_BYTES:
            raise RuntimeError("control response too large")
        sock.sendall(raw)

    def _read_line(self, sock):
        chunks = bytearray()
        while not self._stop.is_set():
            try:
                byte = sock.recv(1)
            except socket.timeout:
                if chunks:
                    continue
                return None
            if not byte:
                raise OSError("control socket closed")
            if byte == b"\n":
                break
            chunks.extend(byte)
            if len(chunks) > _MAX_LINE_BYTES:
                raise RuntimeError("control request too large")
        if not chunks:
            return {}
        value = json.loads(chunks.decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("control message must be an object")
        return value

    def _physics_available(self):
        try:
            return bool(omni.kit.app.get_app().get_extension_manager().is_extension_enabled("omni.physx"))
        except Exception:
            return False

    def _on_log(self, source, level, filename, line_number, message):
        # Carbonite can call this from any thread. Never call Kit/USD/log again here.
        self._telemetry.log(source, level, message)

    def _flush_events(self, sock):
        for event in self._telemetry.drain(24):
            self._send(sock, {"type": "event", "event": event})

    def _on_update(self, event):
        now = time.monotonic()
        if self._previous_update is not None:
            ms = (now - self._previous_update) * 1000
            self._update_ms = ms if not self._update_ms else self._update_ms * 0.9 + ms * 0.1
        self._previous_update = now
        if now < self._sample_at:
            return
        self._sample_at = now + 0.25
        try:
            snapshot = self._scene_service.sample() if omni.usd.get_context().get_stage() else {"stageId": None}
            snapshot.update({"kitUpdateMs": round(self._update_ms, 2),
                             "updateHz": round(1000 / self._update_ms, 1) if self._update_ms else None,
                             "telemetryDropped": self._telemetry.dropped,
                             "physicsRuntimeAvailable": self._physics_available()})
            self._telemetry.emit("telemetry", snapshot)
        except Exception as exc:
            if now - self._telemetry_error_at >= 5:
                self._telemetry_error_at = now
                self._telemetry.emit("telemetry_error", {"message": sanitize(exc)})

    async def _dispatch(self, method, params):
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        read_methods = {"simulation.state", "camera.list", "scene.inspect", "scene.prim", "scene.diagnose"}
        if getattr(self, "_quiescing", False) and method not in read_methods | {"runtime.prepare_stop"}:
            raise RuntimeError("runtime_quiescing: Mutations are blocked until this Kit session exits")
        scene_methods = {
            "scene.inspect": "inspect", "scene.prim": "inspect_prim", "scene.preview": "preview",
            "scene.apply": "apply", "scene.undo": "undo", "scene.export": "export",
            "scene.discard": "discard", "scene.watch": "watch", "scene.run": "run",
            "scene.diagnose": "diagnose",
        }
        if method in scene_methods:
            started = time.monotonic()
            try:
                value = getattr(self._scene_service, scene_methods[method])(params)
                self._telemetry.emit("command", {"method": method, "ok": True,
                                                "durationMs": round((time.monotonic()-started)*1000, 1)})
                return value
            except Exception as exc:
                self._telemetry.emit("command", {"method": method, "ok": False, "message": sanitize(exc)})
                raise
        if method == "stage.open":
            return await self._open_stage(params)
        if method == "simulation.state":
            return self._simulation_state()
        if method == "simulation.configure":
            return self._simulation_configure(params)
        if method == "simulation.control":
            return self._simulation_control(params)
        if method == "timeline.control":
            return self._timeline_control(params)
        if method == "camera.list":
            return self._camera_list()
        if method == "camera.select":
            return self._camera_select(params)
        if method == "camera.navigate":
            return self._camera_navigate(params)
        if method == "camera.save":
            return await self._camera_save()
        if method == "runtime.prepare_stop":
            return self._prepare_stop()
        raise ValueError(f"unsupported control method: {method}")

    async def _open_stage(self, params):
        if getattr(self, "_scene_service", None) and omni.usd.get_context().get_stage():
            if self._scene_service.identity()["hasSessionEdits"]:
                raise ValueError("unsaved_scene_edits: Export then explicitly discard managed edits before replacing the stage")
        stage_path = self._validated_stage(params.get("path"))
        context = omni.usd.get_context()
        ok, error = await context.open_stage_async(str(stage_path))
        if not ok:
            raise RuntimeError(error or "Kit could not open the USD stage")
        await omni.kit.app.get_app().next_update_async()
        self._selected_camera = None
        self._camera_dirty = False
        result = self._simulation_state()
        result.update({"stagePath": str(stage_path), "message": "USD stage loaded in Kit."})
        return result

    def _timeline(self):
        return omni.timeline.get_timeline_interface()

    def _stage(self):
        stage = omni.usd.get_context().get_stage()
        if not stage:
            raise RuntimeError("No USD stage is loaded.")
        return stage

    def _simulation_state(self):
        timeline = self._timeline()
        stage = omni.usd.get_context().get_stage()
        stage_path = ""
        cameras = []
        if stage:
            root = stage.GetRootLayer()
            stage_path = root.realPath or root.identifier or ""
            cameras = self._camera_paths(stage)
        try:
            target_fps = float(timeline.get_target_framerate())
        except Exception:
            target_fps = None
        try:
            tcps = float(timeline.get_time_codes_per_second())
        except Exception:
            tcps = float(stage.GetTimeCodesPerSecond()) if stage else None
        state = "playing" if timeline.is_playing() else ("stopped" if timeline.is_stopped() else "paused")
        return {
            "stagePath": stage_path,
            "state": state,
            "timeSeconds": float(timeline.get_current_time()),
            "rateMultiplier": float(self._rate_multiplier),
            "rateSemantics": "target-frame-cadence-not-physical-time-scale",
            "targetFramerate": target_fps,
            "initialTimeSeconds": float(self._initial_time_seconds),
            "loop": bool(timeline.is_looping()),
            "playEveryFrame": bool(timeline.get_play_every_frame()),
            "timeline": {
                "currentTime": float(timeline.get_current_time()),
                "startTime": float(timeline.get_start_time()),
                "endTime": float(timeline.get_end_time()),
                "timeCodesPerSecond": tcps,
                "targetFrameRate": target_fps,
                "rateMultiplier": float(self._rate_multiplier),
                "isPlaying": bool(timeline.is_playing()),
            },
            "cameras": cameras,
            "selectedCamera": self._selected_camera,
            "cameraDirty": bool(self._camera_dirty),
            "controlBridgeConnected": True,
        }

    def _set_rate_multiplier(self, timeline, multiplier):
        multiplier = float(multiplier)
        if multiplier < 0.05 or multiplier > 8:
            raise ValueError("rateMultiplier must be between 0.05 and 8")
        try:
            current = float(timeline.get_target_framerate())
        except Exception:
            current = 0.0
        if self._base_target_fps is None:
            self._base_target_fps = current if current > 0 else 60.0
        timeline.set_target_framerate(max(1.0, self._base_target_fps * multiplier))
        self._rate_multiplier = multiplier

    def _simulation_configure(self, params):
        timeline = self._timeline()
        initial_time = float(params.get("initialTimeSeconds", 0.0))
        if initial_time < 0:
            raise ValueError("initialTimeSeconds must be non-negative")
        rate = float(params.get("rateMultiplier", 1.0))
        loop = params.get("loop", False)
        play_every_frame = params.get("playEveryFrame", False)
        auto_play = params.get("autoPlay", False)
        if not isinstance(loop, bool) or not isinstance(play_every_frame, bool) or not isinstance(auto_play, bool):
            raise ValueError("loop, playEveryFrame and autoPlay must be booleans")

        self._initial_time_seconds = initial_time
        timeline.set_current_time(initial_time)
        timeline.set_looping(loop)
        timeline.set_play_every_frame(play_every_frame)
        self._set_rate_multiplier(timeline, rate)

        camera_path = params.get("cameraPath")
        if camera_path:
            self._camera_select({"cameraPath": camera_path})

        if auto_play:
            timeline.play()
        else:
            timeline.pause()
        timeline.commit()
        result = self._simulation_state()
        result["message"] = "Simulation session configuration applied."
        return result

    def _simulation_control(self, params):
        action = params.get("action")
        timeline = self._timeline()
        if action == "play":
            timeline.play()
        elif action == "pause":
            timeline.pause()
        elif action == "stop":
            timeline.stop()
        elif action == "reset":
            timeline.stop()
            timeline.set_current_time(self._initial_time_seconds)
        elif action == "step_forward":
            timeline.forward_one_frame()
        elif action == "step_back":
            timeline.rewind_one_frame()
        elif action == "seek":
            value = float(params.get("timeSeconds", -1))
            if value < 0:
                raise ValueError("timeSeconds must be non-negative")
            timeline.set_current_time(value)
        elif action == "set_rate":
            self._set_rate_multiplier(timeline, params.get("rateMultiplier", 0))
        elif action == "set_loop":
            loop = params.get("loop")
            if not isinstance(loop, bool):
                raise ValueError("loop must be a boolean")
            timeline.set_looping(loop)
        else:
            raise ValueError("unsupported simulation action")
        timeline.commit()
        result = self._simulation_state()
        result["message"] = "Simulation session control updated."
        return result

    def _timeline_control(self, params):
        action = params.get("action")
        timeline = self._timeline()
        if action == "play":
            timeline.play()
        elif action == "pause":
            timeline.pause()
        elif action == "stop":
            timeline.stop()
        elif action == "step_forward":
            timeline.forward_one_frame()
        elif action == "step_back":
            timeline.rewind_one_frame()
        elif action == "seek":
            value = float(params.get("timeSeconds", -1))
            if value < 0:
                raise ValueError("timeSeconds must be non-negative")
            timeline.set_current_time(value)
        elif action == "set_rate":
            self._set_rate_multiplier(timeline, params.get("rateMultiplier", 0))
        else:
            raise ValueError("unsupported timeline action")
        timeline.commit()
        result = self._simulation_state()
        result["message"] = "Timeline session updated."
        return result

    def _camera_paths(self, stage):
        values = []
        for prim in stage.Traverse():
            if prim.IsA(UsdGeom.Camera):
                path = prim.GetPath().pathString
                values.append({"path": path, "label": prim.GetName()})
        return values[:512]

    def _camera_list(self):
        result = self._simulation_state()
        result["message"] = "Camera list refreshed."
        return result

    def _camera_prim(self):
        if not self._selected_camera:
            raise RuntimeError("No existing camera is selected.")
        prim = self._stage().GetPrimAtPath(self._selected_camera)
        if not prim or not prim.IsA(UsdGeom.Camera):
            raise RuntimeError("The selected camera no longer exists.")
        return prim

    def _camera_select(self, params):
        path_value = params.get("cameraPath")
        if not isinstance(path_value, str) or not path_value.startswith("/"):
            raise ValueError("cameraPath must be an absolute USD prim path")
        stage = self._stage()
        prim = stage.GetPrimAtPath(path_value)
        if not prim or not prim.IsA(UsdGeom.Camera):
            raise ValueError("cameraPath does not identify an existing USD camera")
        if self._camera_dirty and self._selected_camera and self._selected_camera != path_value:
            raise ValueError("The current camera has unsaved session navigation. Save it before selecting another camera.")
        viewport = get_active_viewport()
        if viewport:
            viewport.camera_path = path_value
        self._selected_camera = path_value
        result = self._simulation_state()
        result["camera"] = {
            "path": path_value,
            "label": prim.GetName(),
            "dirty": bool(self._camera_dirty),
            "saveAvailable": bool(self._camera_dirty),
        }
        result["message"] = "Existing USD camera selected."
        return result

    def _camera_matrix(self, prim):
        xform = UsdGeom.Xformable(prim)
        matrix = xform.GetLocalTransformation()
        # Recent USD Python returns Matrix4d, older bindings may return (matrix, reset).
        if isinstance(matrix, tuple):
            matrix = matrix[0]
        return Gf.Matrix4d(matrix)

    def _author_session_matrix(self, prim, matrix):
        stage = self._stage()
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            xform = UsdGeom.Xformable(prim)
            op = xform.MakeMatrixXform()
            op.Set(matrix)

    def _camera_navigate(self, params):
        prim = self._camera_prim()
        mode = params.get("mode")
        matrix = self._camera_matrix(prim)
        translation = matrix.ExtractTranslation()
        if mode == "dolly":
            amount = float(params.get("amount", 0))
            forward = Gf.Vec3d(-matrix[2][0], -matrix[2][1], -matrix[2][2])
            if forward.GetLength() > 0:
                forward.Normalize()
            matrix.SetTranslateOnly(translation + forward * (amount * 4.0))
        elif mode in ("pan", "orbit"):
            horizontal = float(params.get("horizontal", 0))
            vertical = float(params.get("vertical", 0))
            if mode == "pan":
                right = Gf.Vec3d(matrix[0][0], matrix[0][1], matrix[0][2])
                up = Gf.Vec3d(matrix[1][0], matrix[1][1], matrix[1][2])
                matrix.SetTranslateOnly(translation + right * (horizontal * 3.0) + up * (vertical * 3.0))
            else:
                rotation = Gf.Rotation(Gf.Vec3d(0, 1, 0), horizontal * 22.5) * Gf.Rotation(Gf.Vec3d(1, 0, 0), -vertical * 22.5)
                rotation_matrix = Gf.Matrix4d(1.0)
                rotation_matrix.SetRotate(rotation)
                matrix = matrix * rotation_matrix
        else:
            raise ValueError("unsupported camera navigation mode")
        self._author_session_matrix(prim, matrix)
        self._camera_dirty = True
        result = self._simulation_state()
        result["camera"] = {
            "path": self._selected_camera,
            "label": prim.GetName(),
            "dirty": True,
            "saveAvailable": True,
        }
        result["message"] = "Camera pose updated in the session layer only."
        return result

    async def _camera_save(self):
        prim = self._camera_prim()
        stage = self._stage()
        matrix = self._camera_matrix(prim)
        session = stage.GetSessionLayer()
        target_layer = None
        for spec in prim.GetPrimStack():
            if spec.layer != session and not spec.layer.anonymous and spec.layer.permissionToEdit:
                target_layer = spec.layer
                break
        if target_layer is None:
            root = stage.GetRootLayer()
            if root != session and not root.anonymous and root.permissionToEdit:
                target_layer = root
        if target_layer is None:
            raise RuntimeError("No writable USD source layer owns the selected camera.")
        if target_layer.realPath:
            target = pathlib.Path(target_layer.realPath).resolve(strict=True)
            try:
                target.relative_to(self._allowed_root)
            except ValueError as exc:
                raise RuntimeError("Camera source layer is outside the authorized workspace") from exc
        with Usd.EditContext(stage, target_layer):
            UsdGeom.Xformable(prim).MakeMatrixXform().Set(matrix)
        if not target_layer.Save():
            raise RuntimeError("The camera layer could not be saved.")
        # Remove only OmniStream's temporary camera override after a successful
        # explicit save so the persisted source layer becomes authoritative.
        with Usd.EditContext(stage, session):
            for name in ("xformOp:transform", "xformOpOrder"):
                prop = session.GetPropertyAtPath(prim.GetPath().AppendProperty(name))
                if prop:
                    prim.RemoveProperty(name)
        self._camera_dirty = False
        await omni.kit.app.get_app().next_update_async()
        result = self._simulation_state()
        result["saved"] = True
        result["camera"] = {
            "path": self._selected_camera,
            "label": prim.GetName(),
            "dirty": False,
            "saveAvailable": False,
        }
        result["message"] = "Selected camera pose saved to its writable USD layer."
        return result

    def _prepare_stop(self):
        self._quiescing = True
        timeline = self._timeline()
        try:
            timeline.pause()
            timeline.commit()
        except Exception:
            pass
        return {"prepared": True, "controlBridgeConnected": True, "message": "Runtime prepared for safe stop."}

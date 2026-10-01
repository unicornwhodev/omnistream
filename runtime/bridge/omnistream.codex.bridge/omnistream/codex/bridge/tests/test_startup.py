import os
import tempfile
import pathlib
from unittest.mock import patch

import omni.kit.test
import omni.usd
from pxr import Gf, Usd, UsdGeom
from .. import extension


class TestBridgeStartup(omni.kit.test.AsyncTestCase):
    async def test_camera_save_keeps_a_valid_current_prim(self):
        with tempfile.TemporaryDirectory() as root:
            filename = pathlib.Path(root) / "camera.usda"
            authored = Usd.Stage.CreateNew(str(filename))
            camera = UsdGeom.Camera.Define(authored, "/World/Camera")
            camera.AddTranslateOp().Set(Gf.Vec3d(0, -5, 2))
            authored.GetRootLayer().Save()
            before = filename.read_bytes()
            context = omni.usd.get_context()
            ok, error = await context.open_stage_async(str(filename))
            self.assertTrue(ok, error)
            bridge = extension.OmniStreamCodexBridgeExtension()
            with patch.dict(os.environ, {"CODEX_OMNIVERSE_CONTROL_TOKEN": ""}), \
                    patch.object(extension, "_setting", side_effect=lambda name, default=None: default):
                bridge.on_startup("qualification")
            bridge._allowed_root = pathlib.Path(root)
            try:
                bridge._camera_select({"cameraPath": "/World/Camera"})
                bridge._camera_navigate({"mode": "orbit", "horizontal": 0.05, "vertical": 0.0})
                result = await bridge._camera_save()
                self.assertTrue(result["saved"])
                self.assertEqual(result["camera"]["label"], "Camera")
                self.assertTrue(context.get_stage().GetPrimAtPath("/World/Camera").IsA(UsdGeom.Camera))
                self.assertNotEqual(filename.read_bytes(), before)
                self.assertFalse(bridge._camera_dirty)
            finally:
                bridge.on_shutdown()
                await context.close_stage_async()

    async def test_unconfigured_bridge_stays_disabled(self):
        bridge = extension.OmniStreamCodexBridgeExtension()
        with patch.dict(os.environ, {"CODEX_OMNIVERSE_CONTROL_TOKEN": ""}), \
                patch.object(extension, "_setting", side_effect=lambda name, default=None: default), \
                patch.object(extension.carb, "log_info") as info, \
                patch.object(extension.carb, "log_error") as error:
            bridge.on_startup("qualification")
            self.assertIsNone(bridge._thread)
            self.assertIsNone(bridge._socket)
            self.assertFalse(hasattr(bridge, "_scene_service"))
            info.assert_called_once()
            error.assert_not_called()
            bridge.on_shutdown()

    async def test_non_loopback_host_stays_disabled(self):
        with tempfile.TemporaryDirectory() as root:
            values = {"allowedRoot": root, "controlHost": "0.0.0.0", "controlPort": 12345}
            bridge = extension.OmniStreamCodexBridgeExtension()
            with patch.dict(os.environ, {"CODEX_OMNIVERSE_CONTROL_TOKEN": "x" * 32}), \
                    patch.object(extension, "_setting", side_effect=lambda name, default=None: values.get(name, default)), \
                    patch.object(extension.carb, "log_error") as error:
                bridge.on_startup("qualification")
                self.assertIsNone(bridge._thread)
                self.assertIsNone(bridge._socket)
                self.assertFalse(hasattr(bridge, "_scene_service"))
                error.assert_called_once()
                bridge.on_shutdown()

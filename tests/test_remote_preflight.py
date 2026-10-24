"""Exercise the native host preflight against real USD without booting Kit."""
import ast
import importlib.util
import math
import pathlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
HAS_USD=importlib.util.find_spec('pxr') is not None


@unittest.skipUnless(HAS_USD,'Real OpenUSD is required for host preflight tests')
class RemotePreflightTests(unittest.TestCase):
    def test_native_validation_is_read_only_bounded_and_confined_to_its_workspace(self):
        from pxr import Usd,UsdGeom
        source=ROOT/'runtime/bridge/omnistream.codex.bridge/omnistream/codex/bridge/extension.py'
        tree=ast.parse(source.read_text())
        bridge=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OmniStreamCodexBridgeExtension')
        methods=[n for n in bridge.body if isinstance(n,ast.FunctionDef) and n.name in ['_simulation_preflight','_validated_stage']]
        self.assertEqual(len(methods),2)
        namespace={'pathlib':pathlib,'math':math,'Usd':Usd,'UsdGeom':UsdGeom,'_ALLOWED_USD':{'.usd','.usda','.usdc','.usdz'}}
        exec(compile(ast.Module(body=methods,type_ignores=[]),str(source),'exec'),namespace)
        Native=type('NativeHostMethods',(),{n.name:namespace[n.name] for n in methods})
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);allowed=root/'pilot';allowed.mkdir();other=root/'other';other.mkdir()
            for base in [allowed,other]:
                stage=Usd.Stage.CreateNew(str(base/'scene.usda'));UsdGeom.Xform.Define(stage,'/World');UsdGeom.Camera.Define(stage,'/World/Cameras/A');stage.GetRootLayer().Save()
            instance=Native();instance._allowed_root=allowed.resolve()
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.usda')}
            params={'name':'Pilot renderer test','workspaceRoot':str(allowed),'stagePath':'scene.usda','cameraPath':'/World/Cameras/A','initialTimeSeconds':4_000_000,'rateMultiplier':1,'autoPlay':False}
            result=instance._simulation_preflight(params)
            self.assertTrue(result['ready']);self.assertEqual(result['configuration']['stagePath'],str(allowed/'scene.usda'))
            self.assertEqual(result['configuration']['initialTimeSeconds'],4_000_000)
            for change in [{'stagePath':str(other/'scene.usda')},{'workspaceRoot':str(other)},
                           {'cameraPath':'/World/Missing'},{'rateMultiplier':float('nan')},{'initialTimeSeconds':True},
                           {'rateMultiplier':9},{'autoPlay':1},{'name':'bad\nname'},{'script':'arbitrary execution'}]:
                with self.subTest(change=change),self.assertRaises((ValueError,FileNotFoundError)):
                    instance._simulation_preflight({**params,**change})
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.usda')})


if __name__=='__main__':unittest.main()

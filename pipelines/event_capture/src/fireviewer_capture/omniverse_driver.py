"""Real Replicator manual writers. Imported only inside a compatible Kit app."""
from dataclasses import dataclass
import asyncio
from concurrent.futures import Future
import importlib.metadata
import os
from pathlib import Path
import threading
import time
import numpy as np

from .drivers import RenderDriver,RenderBatch
from .models import ContractError
from .usd_cameras import read_camera
from .residency import require_residency_contract


@dataclass
class Product:
    camera_id:str
    product:object
    writer:object
    enabled:bool=False
    primed:bool=False


class OmniverseRenderDriver(RenderDriver):
    """No simulated front API, no main-viewport camera switching.

    An optional GPU timing provider must return real profiler timestamps. If it
    is absent, render wall time is measured and GPU execution time stays null.
    """
    def __init__(self,gpu_timing_provider=None,residency_provider=None):
        self.rep=None;self.stage=None;self.products=[];self.unsolicited_callbacks=0
        self.gpu_timing_provider=gpu_timing_provider
        self.residency_provider=residency_provider

    async def initialize(self,config):
        if config.get("execution_environment")=="colab" and not (os.name=="posix" and Path("/content").is_dir()):
            raise RuntimeError("This scenario keeps Kit and capture execution on Colab")
        import omni.replicator.core as rep
        import omni.usd
        self.rep=rep;self.stage=omni.usd.get_context().get_stage()
        if self.stage is None:raise RuntimeError("Open the configured USD scene in Kit before starting capture")
        root_path=Path(self.stage.GetRootLayer().realPath)
        if (root_path.parent/'omnistream-geographic.json').is_file() and self.residency_provider is None:
            raise ContractError('Tiled scientific capture needs a validated visibility-complete asset residency provider; the interactive near-camera policy is insufficient')
        rep.orchestrator.set_capture_on_play(False)
        rep.set_global_seed(config['seed'])
        try:version=importlib.metadata.version("isaacsim")
        except importlib.metadata.PackageNotFoundError:version=None
        self.descriptor={"native_omniverse":True,"kind":"NVIDIA Omniverse Replicator",
                         "isaacsim_version":version,"viewport_camera_modified":False,
                         "automatic_capture_on_play":False,"writer_trigger":"manual schedule_write",
                         "gpu_execution_timing_available":self.gpu_timing_provider is not None}
        # Camera creation is a separate preparation action, never an implicit
        # fallback in the renderer. An absent fixed camera is a hard error.
        for camera in config["cameras"]:
            actual=read_camera(self.stage,camera,config)
            matrix=np.asarray(actual["camera_to_world_usd_row_vector"])
            if not np.allclose(matrix[3,:3],camera["position_m"],atol=1e-5,rtol=0):
                raise ContractError("Fixed camera position differs from its configuration")
            desired=np.asarray(camera["look_at_m"])-np.asarray(camera["position_m"]);desired=desired/np.linalg.norm(desired)
            if not np.allclose(-matrix[2,:3],desired,atol=1e-5,rtol=0):
                raise ContractError("Fixed camera orientation differs from its configuration")
            if abs(actual["focal_length_mm"]-camera["focal_length_mm"])>1e-4:
                raise ContractError("Camera focal length differs from its explicit virtual design")
            prim=self.stage.GetPrimAtPath(camera["usd_path"])
            while prim and not prim.IsPseudoRoot():
                if any(a.GetName().startswith("xformOp:") and a.GetNumTimeSamples()>0 for a in prim.GetAttributes()):
                    raise ContractError("This configuration requires fixed USD cameras and fixed ancestors")
                prim=prim.GetParent()

    def camera_metadata(self,camera,config):return read_camera(self.stage,camera,config)

    async def prepare_batch(self,handles,contexts,config):
        if self.residency_provider:
            fingerprints={c.get('state_fingerprint') for c in contexts.values()}
            if len(fingerprints)!=1 or None in fingerprints:
                raise ContractError('Residency preparation requires one explicit frozen state')
            receipt=await self.residency_provider.prepare(self.stage,tuple(contexts.values()),config)
            require_residency_contract(receipt,next(iter(fingerprints)))
        import omni.usd
        reset=getattr(omni.usd.get_context(),'reset_renderer_accumulation',None)
        if not callable(reset):raise ContractError('This Kit runtime needs a qualified renderer-accumulation reset binding')
        reset()

    async def create_product(self,camera,config):
        rep=self.rep;owner=self
        # In the qualified Isaac Sim 5.1 SDK, a writer attached while the
        # orchestrator is STEPPED starts with its trigger already set. Pause
        # only capture orchestration before attaching new writers. Stopping
        # it would repeat asset initialization for every cache eviction.
        status=rep.orchestrator.get_status()
        if status==rep.orchestrator.Status.STEPPED:
            import omni.timeline
            timeline=omni.timeline.get_timeline_interface()
            before=timeline.get_current_time()
            rep.orchestrator.pause()
            if not rep.orchestrator.get_is_paused() or abs(timeline.get_current_time()-before)>1e-9:
                raise ContractError('Capture graph pause failed or changed the simulation time')
        elif status not in [rep.orchestrator.Status.STOPPED,rep.orchestrator.Status.PAUSED]:
            raise ContractError('Capture graph is busy; cannot attach a new manual writer')
        class ManualRGBWriter(rep.Writer):
            def __init__(self):
                self.annotators=[rep.AnnotatorRegistry.get_annotator("rgb")]
                self.data_structure="legacy";self.pending=None;self.lock=threading.Lock()
            def write_metadata(self,*args,**kwargs):
                # The capture store commits its own verified metadata schema.
                # This in-memory RGB writer intentionally has no SDK backend.
                pass
            def arm(self):
                with self.lock:
                    if self.pending is not None:raise ContractError("Writer already armed")
                    self.pending=Future();return self.pending
            def disarm(self):
                with self.lock:
                    pending=self.pending;self.pending=None
                if pending and not pending.done():pending.cancel()
            def write(self,data):
                with self.lock:
                    pending=self.pending;self.pending=None
                if pending is None:
                    owner.unsolicited_callbacks+=1;return
                try:
                    keys=[key for key in data if key=="rgb" or key.startswith("rgb-")]
                    if len(keys)!=1:raise ContractError("Manual RGB writer received missing/ambiguous data")
                    array=np.asarray(data[keys[0]])
                    if array.dtype!=np.uint8 or array.ndim!=3 or array.shape[2]<3:
                        raise ContractError("Replicator returned invalid RGB")
                    pending.set_result(array[:,:,:3].copy())
                except Exception as e:pending.set_exception(e)
        product=rep.create.render_product(camera["usd_path"],tuple(config["render"]["resolution_px"]),force_new=True,name="FV_"+camera["id"])
        product.hydra_texture.set_updates_enabled(False)
        writer=ManualRGBWriter()
        try:writer.attach(product,trigger=None)
        except Exception:
            product.destroy();raise
        handle=Product(camera["id"],product,writer);self.products.append(handle)
        return handle

    def set_updates(self,handle,enabled):
        handle.product.hydra_texture.set_updates_enabled(bool(enabled));handle.enabled=bool(enabled)

    async def trigger(self,handles,contexts,config):
        if any(p.enabled and p.camera_id not in handles for p in self.products):
            raise ContractError("An inactive product is still updating")
        if len([p for p in self.products if p.enabled])>config["render"]["max_active_products"]:
            raise ContractError("Too many active products")
        futures={};gpu_token=None;started=time.perf_counter();before=self.unsolicited_callbacks
        try:
            if self.gpu_timing_provider:
                gpu_token=self.gpu_timing_provider.begin(tuple(p.product.path for p in handles.values()))
            if any(not p.primed for p in handles.values()):
                # Manual writer events require an initialized/stepped graph.
                # A newly attached writer otherwise loses its first event.
                # No writer is armed or scheduled during this single priming
                # frame; it cannot create an accepted image or advance time.
                await asyncio.wait_for(self.rep.orchestrator.step_async(delta_time=0.0,rt_subframes=1),
                                       timeout=config['render'].get('initialization_timeout_wall_s',300))
                if self.unsolicited_callbacks!=before:
                    raise ContractError('A manual writer fired during its unscheduled priming frame')
                for p in handles.values():p.primed=True
            for key,p in handles.items():
                if not p.enabled:raise ContractError("Requested Render Product is disabled")
                futures[key]=p.writer.arm();p.writer.schedule_write()
            await asyncio.wait_for(self.rep.orchestrator.step_async(delta_time=0.0,rt_subframes=config["render"]["rt_subframes"]),
                                   timeout=config['render'].get('render_timeout_wall_s',300))
            # Stop all managed rendering before image encoding or disk writes.
            for p in handles.values():self.set_updates(p,False)
            try:
                frames={key:await asyncio.wait_for(asyncio.wrap_future(future),timeout=config["render"].get("writer_timeout_wall_s",60)) for key,future in futures.items()}
            except TimeoutError:
                missing=sorted(key for key,future in futures.items() if not future.done() or future.cancelled())
                raise ContractError('Explicit RGB writer timed out for cameras: '+', '.join(missing)) from None
            if self.unsolicited_callbacks!=before:raise ContractError("An automatic/unscheduled writer callback occurred")
            gpu=None;source=None
            if self.gpu_timing_provider:
                measured=self.gpu_timing_provider.end(gpu_token)
                if not measured.get("measured") or measured["execution_seconds"]<0:
                    raise ContractError("GPU profiler did not return a real measured duration")
                gpu=measured["execution_seconds"];source=measured["source"]
            return RenderBatch(frames,time.perf_counter()-started,gpu,source)
        finally:
            for p in handles.values():self.set_updates(p,False);p.writer.disarm()

    async def destroy_product(self,handle):
        self.set_updates(handle,False)
        try:handle.writer.detach()
        finally:
            handle.product.destroy()
            self.products=[p for p in self.products if p is not handle]

    async def close(self):
        for p in list(self.products):await self.destroy_product(p)

"""Bounded Render Product pool and verified same-state five-camera groups."""
from collections import OrderedDict
import asyncio
import io
import time
import copy
from PIL import Image
import numpy as np

from .models import digest,utc_at,ContractError


class ReplicatorCaptureManager:
    def __init__(self,config,driver,store,metrics):
        self.config=config;self.driver=driver;self.store=store;self.metrics=metrics
        self.cameras={c["id"]:c for c in config["cameras"]};self.zones={z["id"]:z for z in config["zones"]}
        self.pool=OrderedDict();self.enabled=set();self.initialized=False
        self.config_sha256=digest(config)

    async def start(self):
        if not self.initialized:await self.driver.initialize(self.config);self.initialized=True

    async def _product(self,identifier):
        if identifier in self.pool:
            self.pool.move_to_end(identifier);return self.pool[identifier]
        limit=self.config["render"]["max_cached_products"]
        while len(self.pool)>=limit:
            old,handle=self.pool.popitem(last=False)
            if old in self.enabled:raise ContractError("Attempted to evict an active Render Product")
            await self.driver.destroy_product(handle)
        handle=await self.driver.create_product(self.cameras[identifier],self.config)
        self.driver.set_updates(handle,False);self.pool[identifier]=handle
        self.metrics.counts["peak_cached_products"]=max(self.metrics.counts["peak_cached_products"],len(self.pool))
        return handle

    def _disable_all(self):
        for handle in self.pool.values():self.driver.set_updates(handle,False)
        self.enabled.clear()

    def _context(self,request,camera,snapshot):
        fronts=[f for f in snapshot.state.fronts if f.front_id in request.front_ids]
        # Activity/overlap supplies a trigger, never a visible-flame label.
        annotations=[]
        from dataclasses import asdict
        for f in fronts:
            supplied=copy.deepcopy(f.camera_annotations.get(camera["id"],{}))
            annotations.append({"front_id":f.front_id,"activity":f.activity.value,
                                "provenance":asdict(f.provenance),"camera_annotations":supplied,
                                "flame_visible":supplied.get("flame_visible")})
        return {"schema":"fireviewer.capture-image.v1","scenario_id":self.config["scenario_id"],
                "scene_revision":self.config["scene_revision"],"seed":self.config["seed"],
                "config_sha256":self.config_sha256,"sim_time_us":request.sim_time_us,
                "simulated_utc":utc_at(self.config["period"]["start"],request.sim_time_us),
                "zone_id":request.zone_id,"front_ids":list(request.front_ids),
                "camera":self.driver.camera_metadata(camera,self.config),
                "environment":copy.deepcopy(snapshot.state.environment),
                "trigger":{"reasons":list(request.reasons),"activity":request.activity.value,
                           "priority":request.priority,"scheduled_sim_time_us":request.scheduled_sim_time_us},
                "simulation":{"engine_revision":snapshot.state.engine_revision,
                              "state":copy.deepcopy(snapshot.state.engine_state),"freeze_evidence":snapshot.evidence},
                "state_fingerprint":snapshot.state.fingerprint,
                "render":copy.deepcopy(self.config["render"]),"renderer":copy.deepcopy(self.driver.descriptor),
                "annotations":{"fronts":annotations,"active_front_is_not_visible_flame":True,
                               "unknown_annotations_remain_null":True},"group_commit_required":True}

    def _write(self,capture_id,context,frame):
        if isinstance(frame,(bytes,bytearray)):encoded=bytes(frame)
        else:
            array=np.asarray(frame)
            if array.dtype!=np.uint8 or array.ndim!=3 or array.shape[2]<3:
                raise ContractError("Renderer returned malformed RGB data")
            stream=io.BytesIO();Image.fromarray(array[:,:,:3]).save(stream,format="PNG",compress_level=3);encoded=stream.getvalue()
        return self.store.write_frame(capture_id,context,encoded)

    async def capture_instant(self,adapter,state,requests,on_group_committed=None):
        if not requests:return []
        adapter.require_capture_contract();await self.start()
        if any(r.sim_time_us!=state.sim_time_us or r.state_fingerprint!=state.fingerprint for r in requests):
            raise ContractError("Requests must be grouped at exactly one simulated state")
        cap=self.config["render"]["max_active_products"];completed=[]
        # ONE lease covers all requested groups at this instant, even when the
        # product cap requires several GPU batches. No simulation restart.
        async with adapter.freeze(state) as snapshot:
            for request in requests:
                camera_ids=self.zones[request.zone_id]["camera_ids"];receipts=[]
                contexts={i:self._context(request,self.cameras[i],snapshot) for i in camera_ids}
                needed=[]
                for i in camera_ids:
                    old=self.store.find_frame(digest([self.config_sha256,request.key,i]),contexts[i])
                    if old:receipts.append(old);self.metrics.counts["images_reused_verified"]+=1
                    else:needed.append(i)
                for offset in range(0,len(needed),cap):
                    ids=needed[offset:offset+cap];handles={i:await self._product(i) for i in ids}
                    await adapter.assert_frozen(snapshot);self._disable_all()
                    await self.driver.prepare_batch(handles,{i:contexts[i] for i in ids},self.config)
                    await adapter.assert_frozen(snapshot)
                    try:
                        for i,handle in handles.items():self.driver.set_updates(handle,True);self.enabled.add(i)
                        if len(self.enabled)>cap:raise ContractError("Active render limit exceeded")
                        self.metrics.counts["peak_active_products"]=max(self.metrics.counts["peak_active_products"],len(self.enabled))
                        result=await self.driver.trigger(handles,{i:contexts[i] for i in ids},self.config)
                    finally:
                        self._disable_all()
                    self.metrics.add_render(result.render_wall_s,result.gpu_render_execution_s,result.gpu_timing_source)
                    if set(result.frames)!=set(ids):raise ContractError("Missing or unsolicited camera output")
                    await adapter.assert_frozen(snapshot)
                    started=time.perf_counter()
                    tasks=[]
                    for i in ids:
                        capture_id=digest([self.config_sha256,request.key,i])
                        tasks.append(asyncio.to_thread(self._write,capture_id,contexts[i],result.frames[i]))
                    current=await asyncio.gather(*tasks);receipts.extend(current)
                    self.metrics.durations["encoding_and_write_batch_wall_s"]+=time.perf_counter()-started
                    self.metrics.durations["encoding_and_write_per_image_sum_s"]+=sum(r.write_wall_s for r in current)
                    self.metrics.counts["images_written_new"]+=sum(not r.reused for r in current)
                    self.metrics.counts["images_reused_verified"]+=sum(r.reused for r in current)
                    await adapter.assert_frozen(snapshot)
                group_id=digest([self.config_sha256,request.key]);receipt_hash=self.store.commit_group(group_id,request,receipts,camera_ids)
                completed.append((request,group_id,receipt_hash));self.metrics.counts["groups_committed"]+=1
                if on_group_committed:await on_group_committed(request,group_id,receipt_hash)
        return completed

    async def close(self):
        self._disable_all()
        for handle in list(self.pool.values()):await self.driver.destroy_product(handle)
        self.pool.clear();await self.driver.close()

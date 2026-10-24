"""Verified image commits and atomic checkpoints with idempotent recovery."""
from pathlib import Path
from dataclasses import dataclass
import hashlib
import io
import json
import os
import threading
import time

from PIL import Image

from .models import canonical, digest, identifier, ContractError


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def atomic_bytes(path,content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".part")
    with temporary.open("wb") as f: f.write(content);f.flush();os.fsync(f.fileno())
    expected=hashlib.sha256(content).hexdigest()
    if file_sha(temporary)!=expected: raise IOError("Readback failed before atomic commit")
    os.replace(temporary,path)
    if file_sha(path)!=expected: raise IOError("Readback failed after atomic commit")
    return expected


def atomic_json(path,value):
    return atomic_bytes(path,(canonical(value)+"\n").encode())


@dataclass(frozen=True)
class FrameReceipt:
    capture_id:str
    image_path:str
    metadata_path:str
    image_sha256:str
    metadata_sha256:str
    reused:bool
    write_wall_s:float


class CaptureStore:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self._journal_lock=threading.Lock()

    def _path(self,relative):
        path=self.root/relative
        if not path.resolve().is_relative_to(self.root): raise ContractError("Capture path escaped output directory")
        return path

    def _quarantine(self,path):
        if path.exists():
            target=self.root/"quarantine"/(path.name+"."+str(time.time_ns()))
            target.parent.mkdir(exist_ok=True);os.replace(path,target)

    def find_frame(self,capture_id,metadata):
        started=time.perf_counter();identifier(capture_id)
        folder="frames/"+capture_id[:2];image_rel=folder+"/"+capture_id+".png";meta_rel=folder+"/"+capture_id+".json"
        image=self._path(image_rel);meta=self._path(meta_rel)
        if not image.is_file() or not meta.is_file():return None
        try:
            old=json.loads(meta.read_text())
            same=(old["capture_id"]==capture_id and old["state_fingerprint"]==metadata["state_fingerprint"]
                  and old["config_sha256"]==metadata["config_sha256"] and old.get("write_verified") is True
                  and old["camera"]==metadata["camera"] and old["render"]==metadata["render"]
                  and old["image"]["bytes"]==image.stat().st_size and old["image"]["sha256"]==file_sha(image))
            if same:return FrameReceipt(capture_id,image_rel,meta_rel,file_sha(image),file_sha(meta),True,time.perf_counter()-started)
        except (ValueError,KeyError,OSError):pass
        return None

    def write_frame(self,capture_id,metadata,png_bytes):
        started=time.perf_counter();identifier(capture_id)
        folder="frames/"+capture_id[:2];image_rel=folder+"/"+capture_id+".png";meta_rel=folder+"/"+capture_id+".json"
        image=self._path(image_rel);meta=self._path(meta_rel)
        existing=self.find_frame(capture_id,metadata)
        if existing:return existing
        # Only files in this deterministic output slot are moved; no recursive
        # deletion or overwrite of unverified data is used during recovery.
        for path in [image,meta,image.with_suffix(".png.part"),meta.with_suffix(".json.part")]: self._quarantine(path)
        with Image.open(io.BytesIO(png_bytes)) as decoded:
            decoded.load()
            if decoded.format!="PNG" or list(decoded.size)!=metadata["render"]["resolution_px"]:
                raise ContractError("Encoded frame does not match its declared resolution/format")
        image_hash=atomic_bytes(image,png_bytes)
        record={**metadata,"capture_id":capture_id,"image":{"path":image_rel,"sha256":image_hash,"bytes":len(png_bytes),"format":"png"},"write_verified":True}
        metadata_hash=atomic_json(meta,record)
        self.log({"event":"image_committed","capture_id":capture_id,"image_sha256":image_hash,"sim_time_us":record["sim_time_us"]})
        return FrameReceipt(capture_id,image_rel,meta_rel,image_hash,metadata_hash,False,time.perf_counter()-started)

    def commit_group(self,group_id,request,receipts,expected_camera_ids):
        from dataclasses import asdict
        if len(receipts)!=len(expected_camera_ids) or len(receipts)!=5:
            raise ContractError("A group commit requires all five verified camera images")
        records=[json.loads(self._path(r.metadata_path).read_text()) for r in receipts]
        if {r["camera"]["id"] for r in records}!=set(expected_camera_ids): raise ContractError("Group camera set changed")
        if any(r["sim_time_us"]!=request.sim_time_us or r["state_fingerprint"]!=request.state_fingerprint for r in records):
            raise ContractError("The five camera images do not represent the same frozen simulated state")
        for receipt in receipts:
            if file_sha(self._path(receipt.image_path))!=receipt.image_sha256 or file_sha(self._path(receipt.metadata_path))!=receipt.metadata_sha256:
                raise IOError("A group image or its metadata changed before commit")
        group_path=self._path("groups/"+group_id+".json")
        if group_path.is_file():
            try:
                old=json.loads(group_path.read_text())
                if (old.get("verified") is True and old["state_fingerprint"]==request.state_fingerprint
                        and {r["capture_id"]:r["image_sha256"] for r in old["frames"]}=={r.capture_id:r.image_sha256 for r in receipts}):
                    return file_sha(group_path)
            except (ValueError,KeyError,OSError):pass
            self._quarantine(group_path)
        return atomic_json(group_path,
                           {"schema":"fireviewer.capture-group.v1","group_id":group_id,"zone_id":request.zone_id,
                            "sim_time_us":request.sim_time_us,"state_fingerprint":request.state_fingerprint,
                            "camera_ids":list(expected_camera_ids),"frames":[asdict(r) for r in receipts],"verified":True})

    def checkpoint(self,value): return atomic_json(self.root/"checkpoint.json",{"payload":value,"sha256":digest(value)})
    def read_checkpoint(self):
        p=self.root/"checkpoint.json"
        if not p.is_file():return None
        envelope=json.loads(p.read_text())
        if envelope.get("sha256")!=digest(envelope.get("payload")):
            raise ContractError("Checkpoint checksum mismatch")
        return envelope["payload"]
    def log(self,event):
        with self._journal_lock,(self.root/"events.jsonl").open("a",encoding="utf-8") as f:
            f.write(canonical(event)+"\n");f.flush()

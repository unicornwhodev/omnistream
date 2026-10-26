"""Connect verified cloud offload to the frozen, committed capture boundary."""
import asyncio
import hashlib
import json

from verified_spool import RcloneBackend,VerifiedSpool


async def drained_worker(function,*args):
    """Never abandon a transfer/deletion worker on coroutine cancellation."""
    task=asyncio.create_task(asyncio.to_thread(function,*args))
    try:
        return await asyncio.shield(task)
    except BaseException:
        await task
        raise


class SpoolOffloader:
    def __init__(self,spool,policy):
        self.spool=spool
        self.policy_id=hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    async def admit_group(self,config):
        width,height=config['render']['resolution_px']
        # A conservative bound for five RGBA PNGs (incompressible data), row
        # filters, deflate overhead and metadata. Admission is per group, so
        # ten simultaneous zones do not require fifty resident image files.
        next_group_bytes=5*(width*height*4*2+1_048_576)
        return await drained_worker(self.spool.capacity,next_group_bytes)

    async def offload_group(self,group_id):
        return await drained_worker(self.spool.offload_group,group_id)


def make_offloader(config,store):
    """Private configuration supplies paths/remote/folder; never a raw token."""
    value=config['local_offload']
    backend=RcloneBackend(value['rclone_executable'],value['rclone_config_path'],
                          value['remote'],value['folder_id'])
    spool=VerifiedSpool(store.root,backend,max_bytes=int(value.get('max_spool_bytes',512_000_000)),
                         reserve_bytes=int(value.get('reserve_bytes',16_000_000_000)))
    return SpoolOffloader(spool,{'kind':'drive-readback-sha256-v1','remote':value['remote'],
                                'folder_id':value['folder_id'],'max_spool_bytes':spool.max_bytes,
                                'reserve_bytes':spool.reserve_bytes})

"""Metrics for real repeated-view and resource evidence; never fabricate inputs."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from .models import ContractError
from .storage import file_sha


def compare_repeated_view(metadata_a,metadata_b,mean_abs_limit,p99_abs_limit):
    records=[];arrays=[]
    for path in [metadata_a,metadata_b]:
        p=Path(path);r=json.loads(p.read_text());root=p.parents[2]
        image=root/r['image']['path']
        if file_sha(image)!=r['image']['sha256']:raise ContractError('Repeated-view image checksum mismatch')
        arrays.append(np.asarray(Image.open(image).convert('RGB'),dtype=float));records.append(r)
    a,b=records
    for key in ['state_fingerprint','camera','render']:
        if a[key]!=b[key]:raise ContractError('Repeated-view comparison requires the same frozen state, camera and render settings')
    if arrays[0].shape!=arrays[1].shape:raise ContractError('Repeated-view image sizes differ')
    diff=np.abs(arrays[0]-arrays[1]);mean=float(diff.mean());p99=float(np.percentile(diff,99))
    return {'mean_absolute_RGB_difference_0_255':mean,'p99_absolute_RGB_difference_0_255':p99,
            'thresholds':{'mean':mean_abs_limit,'p99':p99_abs_limit},'passed':mean<=mean_abs_limit and p99<=p99_abs_limit,
            'visual_ghosting_inspection_still_required':True}


def resource_stability(cycle_samples,warmup_cycles,max_rss_growth_bytes_per_cycle,max_vram_growth_bytes_per_cycle):
    rows=[r for r in cycle_samples if r['cycle']>=warmup_cycles]
    if len(rows)<5:raise ContractError('At least five post-warmup cycle measurements are needed')
    x=np.asarray([r['cycle'] for r in rows],dtype=float);x=x-x.mean();den=float(x@x)
    if not den:raise ContractError('Resource samples must cover distinct cycles')
    result={}
    for key,limit in [('process_rss_bytes',max_rss_growth_bytes_per_cycle),('device_vram_used_bytes',max_vram_growth_bytes_per_cycle)]:
        if any(r.get(key) is None for r in rows):result[key]={'measured':False,'passed':False};continue
        y=np.asarray([r[key] for r in rows],dtype=float);slope=float(x@(y-y.mean())/den)
        result[key]={'measured':True,'growth_bytes_per_cycle':slope,'peak_bytes':int(y.max()),'limit_bytes_per_cycle':limit,'passed':slope<=limit}
    result['passed']=all(v['passed'] for v in result.values());return result

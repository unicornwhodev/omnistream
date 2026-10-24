"""Compare planned capture counts. This command performs NO rendering."""
import argparse,asyncio,json
from pathlib import Path
from fireviewer_capture.config import load_config
from fireviewer_capture.benchmark import subset_config,policy_plan
from fireviewer_capture.models import SimulationState


async def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--state-log',required=True)
    p.add_argument('--output',required=True);p.add_argument('--uniform-interval-sim-s',type=float,default=60)
    a=p.parse_args();c=load_config(a.config);states=[SimulationState.from_dict(s) for s in json.loads(Path(a.state_log).read_text())['states']]
    report=[]
    for n in [1,2,5,10]:
        if n>len(c['zones']):continue
        sub=subset_config(c,n);uniform=await policy_plan(sub,states,a.uniform_interval_sim_s);event=await policy_plan(sub,states)
        report.append({'groups':n,'uniform':uniform,'event':event,'planned_image_reduction':1-event['images']/uniform['images'] if uniform['images'] else None})
    Path(a.output).write_text(json.dumps({'trials':report,'GPU_memory_timings_and_quality_not_measured':True},indent=2))


if __name__=='__main__':asyncio.run(main())

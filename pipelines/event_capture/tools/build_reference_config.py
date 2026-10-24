"""Generate an explicit 10x5 CAMERA DESIGN EXAMPLE, not surveyed placements."""
from pathlib import Path
import json

def reference_config():
    zones=[];cameras=[]
    for index in range(10):
        col=index%5;row=index//5;west=-10000+col*4000;south=-10000+row*10000
        centre=[west+2000,south+5000,500]
        zone_id=f"zone_{index+1:02d}";ids=[]
        positions=[(0,-300,180),(-300,0,180),(0,300,180),(300,0,180),(0,-50,8)]
        for number,(dx,dy,dz) in enumerate(positions,1):
            ident=f"{zone_id}_cam_{number:02d}";ids.append(ident)
            cameras.append({"id":ident,"usd_path":"/World/Cameras/"+ident,
                            "position_m":[centre[0]+dx,centre[1]+dy,centre[2]+dz],
                            "look_at_m":centre,"up":[0,0,1],"focal_length_mm":22,
                            "horizontal_aperture_mm":36,"clipping_range_m":[.1,100000],
                            "pose_provenance":"explicit synthetic design example; replace from scene/site configuration"})
        zones.append({"id":zone_id,"geometry":{"type":"Polygon","coordinates":[[[west,south],[west+4000,south],[west+4000,south+10000],[west,south+10000],[west,south]]]},"camera_ids":ids})
    return {"schema":"fireviewer.event-capture-config.v1","scenario_id":"die-justin-reference-47-days",
            "scene_revision":"replace-with-verified-scene-revision","seed":20260624,
            "execution_environment":"colab","period":{"start":"2026-06-24T00:00:00+02:00","end_exclusive":"2026-08-10T00:00:00+02:00","timezone":"Europe/Paris"},
            "acceleration":500,"coordinate_system":"scene_local_metric_Z_up",
            "adapter":{"kind":"missing","reason":"Bind a real simulator adapter; no front API is assumed"},
            "weather":{"provider":"supplied_by_simulation_adapter","observed_and_modelled_sources_must_remain_distinct":True,"missing_values":"null, never fabricated"},
            "activity":{"enter_margin_m":50,"exit_margin_m":150,"enter_hold_sim_s":30,
                        "exit_hold_sim_s":90,"post_extinction_window_sim_s":21600,
                        "poll_interval_sim_s":3600,"requires_stop_on_activity_event":True},
            "capture_policy":{"inactive":{"interval_sim_s":21600,"priority":10},
                              "early_smoke":{"interval_sim_s":300,"priority":80},
                              "active_rapid":{"interval_sim_s":90,"priority":100},
                              "active_stable":{"interval_sim_s":300,"priority":90},
                              "declining":{"interval_sim_s":900,"priority":50},
                              "post_extinction":{"interval_sim_s":1800,"priority":30}},
            "render":{"resolution_px":[1280,720],"channels":["rgb"],"max_active_products":5,
                      "max_cached_products":10,"rt_subframes":8,"writer_timeout_wall_s":60,
                      "renderer":"RayTracedLighting","main_viewport_policy":"unchanged; no camera rotation",
                      "seed":20260624},"zones":zones,"cameras":cameras}

if __name__=="__main__":
    out=Path(__file__).resolve().parents[1]/"examples/reference_50_cameras.json"
    out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(reference_config(),indent=2)+"\n")
    print(f"Wrote {len(reference_config()['cameras'])} explicit camera designs")

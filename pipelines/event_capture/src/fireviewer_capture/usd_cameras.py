"""Read/write explicit virtual camera designs; never rotate the main viewport."""
import math
import numpy as np


def create_configured_cameras(stage,config):
    from pxr import UsdGeom,Gf
    mpu=float(UsdGeom.GetStageMetersPerUnit(stage));width,height=config["render"]["resolution_px"]
    if UsdGeom.GetStageUpAxis(stage)!="Z" or mpu!=1:
        raise ValueError("Reference camera design requires a metric Z-up scene")
    for row in config["cameras"]:
        cam=UsdGeom.Camera.Define(stage,row["usd_path"])
        cam.CreateFocalLengthAttr(row["focal_length_mm"]/(100*mpu))
        cam.CreateHorizontalApertureAttr(row["horizontal_aperture_mm"]/(100*mpu))
        cam.CreateVerticalApertureAttr(row["horizontal_aperture_mm"]*height/width/(100*mpu))
        cam.CreateHorizontalApertureOffsetAttr(0);cam.CreateVerticalApertureOffsetAttr(0)
        cam.CreateFStopAttr(0);cam.CreateClippingRangeAttr(Gf.Vec2f(*row.get("clipping_range_m",[.1,100000])))
        matrix=Gf.Matrix4d().SetLookAt(Gf.Vec3d(*row["position_m"]),Gf.Vec3d(*row["look_at_m"]),Gf.Vec3d(*row["up"])).GetInverse()
        UsdGeom.Xformable(cam).MakeMatrixXform().Set(matrix)


def read_camera(stage,row,config):
    from pxr import UsdGeom,Usd
    cam=UsdGeom.Camera.Get(stage,row["usd_path"])
    if not cam:raise ValueError("Configured USD camera is absent: "+row["id"])
    width,height=config["render"]["resolution_px"];mpu=float(UsdGeom.GetStageMetersPerUnit(stage))
    f=float(cam.GetFocalLengthAttr().Get());h=float(cam.GetHorizontalApertureAttr().Get());v=float(cam.GetVerticalApertureAttr().Get())
    if f<=0 or h<=0 or v<=0 or abs(h/v-width/height)>1e-4:
        raise ValueError("Camera optical dimensions/aspect do not match the Render Product")
    if float(cam.GetHorizontalApertureOffsetAttr().Get())!=0 or float(cam.GetVerticalApertureOffsetAttr().Get())!=0:
        raise ValueError("Nonzero aperture offsets need a separately validated camera model")
    c2w=np.asarray(UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(cam.GetPrim()))
    w2cv=np.diag([1.,-1.,-1.,1.])@np.linalg.inv(c2w.T)
    return {"id":row["id"],"usd_path":row["usd_path"],"pose_source":"actual composed USD camera at frozen capture time",
            "camera_to_world_usd_row_vector":c2w.tolist(),"world_to_camera_cv_column_vector":w2cv.tolist(),
            "intrinsic_K":[[f/h*width,0,width/2],[0,f/v*height,height/2],[0,0,1]],
            "focal_length_mm":f*mpu*100,"sensor_aperture_mm":[h*mpu*100,v*mpu*100],
            "pixel_convention":"upper-left image-edge origin; pixel centres at i+0.5,j+0.5",
            "camera_axes_cv":"X right,Y down,+Z forward","physical_hardware_calibrated":False}

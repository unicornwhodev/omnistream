"""Non-destructive response-test opinions for existing Flow recipes.

The response profile removes imposed upward ambient flow and smoke-only
buoyancy. It is an explicit model setup, not a calibrated heat-release model.
"""
import math


def apply_response_profile(stage, effect_root, *, wind_m_s=(0.0, 0.0, 0.0),
                           source_up_m_s=0.0, hot=True, emission_end_s=None):
    from pxr import Gf, Sdf
    wind = tuple(float(x) for x in wind_m_s)
    if len(wind) != 3 or not all(math.isfinite(x) and abs(x) <= 15 for x in wind):
        raise ValueError('Wind must have three finite components in -15..15 m/s')
    if not math.isfinite(source_up_m_s) or not 0 <= source_up_m_s <= 2:
        raise ValueError('Source injection velocity outside the bounded laboratory range')
    if emission_end_s is not None and (not math.isfinite(emission_end_s) or emission_end_s <= 0):
        raise ValueError('Emission cutoff must be a positive simulated time')
    root = stage.GetPrimAtPath(effect_root)
    if not root:
        raise ValueError('The actual referenced factory effect is missing')
    from pxr import Usd
    changes = []
    voxel_size = next(float(p.GetAttribute('densityCellSize').Get()) for p in Usd.PrimRange(root)
                      if p.GetTypeName() == 'FlowSimulate')

    def set_value(prim, name, value):
        attribute = prim.GetAttribute(name)
        if not attribute:
            raise ValueError('The installed Flow schema lacks ' + str(prim.GetPath()) + '/' + name)
        before = str(attribute.Get())
        attribute.Set(value)
        changes.append({'prim': str(prim.GetPath()), 'attribute': name,
                        'before': before, 'after': str(attribute.Get())})
        return attribute

    for prim in Usd.PrimRange(root):
        kind = prim.GetTypeName()
        if kind == 'FlowSimulate':
            for name, value in {'enableVariableTimeStep': False, 'simulateWhenPaused': False,
                                'forceSimulate': False, 'timeScale': 1.0,
                                'stepsPerSecond': 60.0, 'maxStepsPerSimulate': 8,
                                'velocitySubSteps': 4, 'physicsCollisionEnabled': True,
                                'physicsConvexCollision': False}.items():
                set_value(prim, name, value)
        elif prim.GetName() == 'advection' and prim.GetAttribute('buoyancyPerTemp'):
            set_value(prim, 'gravity', Gf.Vec3f(0, 0, -1))
            set_value(prim, 'buoyancyPerSmoke', 0.0)
            # Retain the factory's thermal coefficient. This test removes
            # artificial smoke-density lift and source velocity constraints;
            # it does not invent a calibrated replacement thermal constant.
            set_value(prim, 'buoyancyPerTemp', float(prim.GetAttribute('buoyancyPerTemp').Get()))
            set_value(prim, 'globalFetch', True)
            if not hot:
                set_value(prim, 'combustionEnabled', False)
        elif kind.startswith('FlowEmitter') and prim.GetName() == 'AmbientWind':
            attr = set_value(prim, 'velocity', Gf.Vec3f(*wind))
            if attr.GetNumTimeSamples():
                raise RuntimeError('A stronger default did not override the animated ambient velocity')
        elif kind.startswith('FlowEmitter') and prim.GetName() == 'GroundCull':
            # Actual PhysX/Flow collision is tested against the reference floor;
            # an eraser below the floor must not masquerade as contact physics.
            set_value(prim, 'enabled', False)
        elif kind.startswith('FlowEmitter') and prim.GetName().startswith('Emitter_'):
            attr = set_value(prim, 'velocity', Gf.Vec3f(wind[0], wind[1], wind[2] + source_up_m_s))
            if source_up_m_s == 0:
                # A scalar/heat source without a specified jet must not clamp
                # its fluid velocity to zero. That suppressed buoyant escape
                # from thin emitters in the native response tests.
                set_value(prim, 'coupleRateVelocity', 0.0)
            if attr.GetNumTimeSamples():
                raise RuntimeError('A stronger default did not override the animated source velocity')
            position = prim.GetAttribute('position').Get()
            if kind == 'FlowEmitterSphere' and float(position[2]) < 5:
                radius = float(prim.GetAttribute('radius').Get())
                prim.SetTypeName('FlowEmitterBox')
                prim.CreateAttribute('halfSize', Sdf.ValueTypeNames.Float3, custom=True).Set(
                    Gf.Vec3f(radius * .65, radius * .45, radius * .15))
                changes.append({'prim': str(prim.GetPath()), 'attribute': 'typeName',
                                'before': kind, 'after': 'FlowEmitterBox'})
            half_height = (float(prim.GetAttribute('radius').Get()) if prim.GetTypeName() == 'FlowEmitterSphere'
                           else float(prim.GetAttribute('halfSize').Get()[2]))
            clearance = half_height + 2 * voxel_size
            if float(position[2]) < clearance:
                set_value(prim, 'position', Gf.Vec3f(float(position[0]), float(position[1]), clearance))
            if not hot:
                set_value(prim, 'temperature', 0.0)
                set_value(prim, 'fuel', 0.0)
            if emission_end_s is not None:
                enabled = prim.GetAttribute('enabled')
                if not enabled:
                    raise ValueError('Source has no enabled attribute')
                enabled.Set(True, 0)
                enabled.Set(False, emission_end_s * stage.GetTimeCodesPerSecond())
    return {'profile': 'flow-response-v3', 'wind_m_s': list(wind),
            'source_up_m_s': source_up_m_s, 'hot': hot, 'emission_end_s': emission_end_s,
            'changes': changes, 'physical_fire_calibrated': False,
            'model_limits': ['Flow temperature and fuel are model fields, not calibrated SI measurements',
                             'Flow gravity establishes the buoyancy direction',
                             'Ambient velocity relaxation is not a calibrated atmospheric boundary layer']}

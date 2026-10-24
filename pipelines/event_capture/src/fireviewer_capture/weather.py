"""Auditable hourly forcing. Observations, estimates and missing data stay distinct."""
from bisect import bisect_right
import copy
import hashlib
import json
import math
from pathlib import Path

from .models import ContractError,aware_time,simulated_us,utc_at,digest


def wind_uv(speed,direction):
    """Meteorological FROM true north -> east/north velocity, without grid rotation."""
    if speed is None:return None,None
    if not math.isfinite(speed) or speed<0:raise ContractError('Invalid wind speed')
    if speed==0:return 0.0,0.0
    if direction is None:return None,None
    if not math.isfinite(direction) or not 0<=direction<=360:
        raise ContractError('Invalid/variable wind direction requires explicit treatment')
    a=math.radians(direction)
    return -speed*math.sin(a),-speed*math.cos(a)


class HourlyWeatherTimeline:
    """Read a verified normalized file, never silently fill gaps or extrapolate.

    ``sample`` means a value associated with the source timestamp (including a
    documented 10-minute wind average). ``preceding_hour_sum/mean/max`` requires
    a verified interval convention. Unresolved aggregates remain unavailable
    for continuous forcing while their raw values remain in the source file.
    """
    def __init__(self,path,expected_sha256=None,accepted_quality_codes=('0','1')):
        raw=Path(path).read_bytes();self.sha256=hashlib.sha256(raw).hexdigest()
        if expected_sha256 and expected_sha256!=self.sha256:raise ContractError('Weather file checksum mismatch')
        self.data=json.loads(raw);d=self.data
        if d.get('schema')!='fireviewer.weather-hourly.v1':raise ContractError('Unknown weather contract')
        if d['source']['kind'] not in ('observed','estimated','test_fixture'):
            raise ContractError('Weather provenance must distinguish observations and estimates')
        self.start=d['period']['start'];self.end_us=simulated_us((aware_time(d['period']['end_exclusive'])-aware_time(self.start)).total_seconds())
        self.rows=d['hours'];self.times=[r['sim_time_us'] for r in self.rows]
        if (len(self.times)<2 or self.times[0]!=0 or self.times[-1]<self.end_us or
                any(type(t) is not int for t in self.times) or
                any(b-a!=3_600_000_000 for a,b in zip(self.times,self.times[1:]))):
            raise ContractError('Weather needs a complete hourly axis including the final boundary sample')
        self.quality=set(accepted_quality_codes)
        if not self.quality.issubset({'0','1','9'}):raise ContractError('Doubtful/unknown weather QC cannot be silently accepted')
        for r in self.rows:
            for name,v in r['values'].items():
                if name not in d['variables']:raise ContractError('Undeclared weather variable')
                if v is not None and (type(v) not in (float,int) or not math.isfinite(v)):
                    raise ContractError('Weather values must be finite numeric values or null')
        self.identity=digest(d)

    def _value(self,row,key):
        value=row['values'].get(key);quality=row.get('quality',{}).get(key)
        if self.data['source']['kind']=='observed' and quality not in self.quality:
            return None,quality,'source_quality_rejected_or_absent'
        return value,quality,'missing_source_value' if value is None else None

    def at(self,sim_time_us):
        if type(sim_time_us) is not int or not 0<=sim_time_us<self.end_us:
            raise ContractError('Weather time must be inside the exclusive simulated period')
        i=bisect_right(self.times,sim_time_us)-1;a=self.rows[i];b=self.rows[i+1]
        alpha=(sim_time_us-self.times[i])/3_600_000_000
        fields={}
        for key,spec in self.data['variables'].items():
            temporal=spec['temporal_support'];av,aq,ae=self._value(a,key);bv,bq,be=self._value(b,key)
            provenance={'source_kind':self.data['source']['kind'],'source_id':self.data['source']['id'],
                        'source_field':spec['source_field'],'dataset_sha256':self.sha256,
                        'temporal_support':temporal,'unit':spec['unit']}
            if temporal=='sample':
                if alpha==0:value=av;error=ae;method='source_sample';quality=[aq];times=[self.times[i]]
                else:
                    value=None if av is None or bv is None else av+(bv-av)*alpha
                    error=ae or be;method='linear_temporal_estimate';quality=[aq,bq];times=self.times[i:i+2]
            elif temporal in ('preceding_hour_sum','preceding_hour_mean','preceding_hour_max'):
                value=bv;error=be;method='constant_distribution_assumption' if temporal.endswith('sum') else 'hourly_aggregate_context'
                quality=[bq];times=[self.times[i+1]]
                provenance['support_interval_sim_us']=[self.times[i],self.times[i+1]]
            else:
                value=None;error='unverified_temporal_support';method='not_used_for_continuous_forcing';quality=[aq,bq];times=self.times[i:i+2]
            fields[key]={'value':value,'quality_codes':quality,'unavailable_reason':error,
                         'method':method,'source_times_sim_us':times,'provenance':provenance}
        # Interpolate wind components, not angles or an inconsistent scalar speed.
        wind=None
        if 'wind_speed_10m_m_s' in fields and 'wind_from_true_north_deg' in fields:
            au,an=wind_uv(self._value(a,'wind_speed_10m_m_s')[0],self._value(a,'wind_from_true_north_deg')[0])
            bu,bn=wind_uv(self._value(b,'wind_speed_10m_m_s')[0],self._value(b,'wind_from_true_north_deg')[0])
            if alpha==0:u,v=au,an
            elif None in (au,an,bu,bn):u=v=None
            else:u,v=au+(bu-au)*alpha,an+(bn-an)*alpha
            speed=None if u is None else math.hypot(u,v)
            direction=None if speed is None or speed<1e-10 else math.degrees(math.atan2(-u,-v))%360
            wind={'east_m_s':u,'north_m_s':v,'speed_m_s':speed,'from_true_north_deg':direction,
                  'method':'linear_ENU_components' if alpha else 'source_sample_to_ENU',
                  'grid_rotation_applied':False,'spatial_field_calibrated':False}
            fields['wind_speed_10m_m_s']['value']=speed;fields['wind_speed_10m_m_s']['method']=wind['method']
            fields['wind_from_true_north_deg']['value']=direction;fields['wind_from_true_north_deg']['method']=wind['method']
        return {'schema':'fireviewer.weather-sample.v1','sim_time_us':sim_time_us,'utc':utc_at(self.start,sim_time_us),
                'source':copy.deepcopy(self.data['source']),'dataset_sha256':self.sha256,'fields':fields,'wind_ENU':wind,
                'spatial_application':'uniform station/grid forcing is an estimate, not a resolved mountain wind field',
                'fuel_moisture_inferred':False}

import copy,json,tempfile,unittest
from pathlib import Path
from fireviewer_capture.weather import HourlyWeatherTimeline,wind_uv
from fireviewer_capture.models import ContractError


def fixture():
    variables={k:{'source_field':k,'unit':unit,'temporal_support':support} for k,unit,support in [
        ('temperature_c','degC','sample'),('wind_speed_10m_m_s','m/s','sample'),
        ('wind_from_true_north_deg','degree','sample'),('rain_mm','mm','preceding_hour_sum'),
        ('unresolved_rain_mm','mm','unverified_hourly_sum')]}
    return {'schema':'fireviewer.weather-hourly.v1','source':{'kind':'observed','id':'test_station'},
            'period':{'start':'2026-06-24T00:00:00+02:00','end_exclusive':'2026-06-24T02:00:00+02:00'},
            'variables':variables,'hours':[{'sim_time_us':i*3_600_000_000,
                'values':{'temperature_c':10+i*10,'wind_speed_10m_m_s':10,
                          'wind_from_true_north_deg':270 if i==0 else 90,'rain_mm':i+1,'unresolved_rain_mm':i+1},
                'quality':{k:'1' for k in variables}} for i in range(3)]}


class WeatherTests(unittest.TestCase):
    def timeline(self,data):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);p=Path(d.name)/'weather.json';p.write_text(json.dumps(data))
        return HourlyWeatherTimeline(p)
    def test_wind_interpolation_stays_vector_consistent_through_reversal(self):
        value=self.timeline(fixture()).at(1_800_000_000)
        self.assertAlmostEqual(value['wind_ENU']['speed_m_s'],0)
        self.assertIsNone(value['wind_ENU']['from_true_north_deg'])
        self.assertAlmostEqual(value['fields']['wind_speed_10m_m_s']['value'],0)
    def test_rain_uses_next_hour_ending_sample_and_boundary_changes(self):
        t=self.timeline(fixture())
        self.assertEqual(t.at(0)['fields']['rain_mm']['value'],2)
        self.assertEqual(t.at(3_600_000_000)['fields']['rain_mm']['value'],3)
        self.assertIsNone(t.at(0)['fields']['unresolved_rain_mm']['value'])
    def test_filtered_quality_is_preserved_but_not_silently_used(self):
        d=fixture();d['hours'][1]['quality']['temperature_c']='9';t=self.timeline(d)
        self.assertEqual(t.at(0)['fields']['temperature_c']['value'],10)
        self.assertIsNone(t.at(1_800_000_000)['fields']['temperature_c']['value'])
        self.assertEqual(t.at(3_600_000_000)['fields']['temperature_c']['quality_codes'],['9'])
    def test_missing_final_boundary_and_extrapolation_are_rejected(self):
        d=fixture();d['hours'].pop()
        with self.assertRaises(ContractError):self.timeline(d)
        with self.assertRaises(ContractError):self.timeline(fixture()).at(7_200_000_000)
    def test_calm_wind_does_not_require_an_invented_direction(self):
        self.assertEqual(wind_uv(0,None),(0,0))
        with self.assertRaises(ContractError):wind_uv(1,999)
    def test_checksum_is_verified(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'weather.json';p.write_text(json.dumps(fixture()))
            with self.assertRaises(ContractError):HourlyWeatherTimeline(p,'0'*64)

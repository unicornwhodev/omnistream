# Weather inputs and provenance

The terrain scenario uses 2026-06-24 00:00 CEST to 2026-08-10 00:00 CEST,
exclusive: 47 days, 1,128 simulated hours. The UTC boundaries are
2026-06-23T22:00:00Z and 2026-08-09T22:00:00Z. Continuous interpolation requires
the additional sample at the final boundary: 1,129 hourly samples.

Météo-France station observations are the primary historical evidence. The
[official hourly archive](https://www.data.gouv.fr/datasets/donnees-climatologiques-de-base-horaires)
provides UTC timestamps and raw quality columns. Keep raw files, retrieval date,
SHA-256, station coordinates, elevation, field names and units. Decimal precision
is not a scale factor: a temperature of 21.4 already means 21.4 °C.

The [official field descriptor](https://meteofrance.s3.sbg.io.cloud.ovh.net/data/synchro_ftp/BASE/HOR/H_descriptif_champs.csv)
defines quality 0 as protected, 1 as validated, 9 as filtered and 2 as doubtful.
Default processing accepts 0 and 1. Filtered values remain in the source but
return null for forcing. An explicitly selected preliminary policy may accept
9; record that policy in the adapter/run configuration. Never fill doubtful or
missing values silently. A complete timestamp axis does not imply complete
validated measurements.

At the acquisition checked on 2026-10-24, Die (26113003, 384 m) has temperature
and rain, but no wind or humidity in this archive. Saint-Roman-Diois (26327001,
545 m, about 8.3 km from Croix de Justin) supplies the wind, temperature,
humidity and precipitation series. Of its 1,128 core-window humidity values,
88 carry quality 9. Preserve that distinction. This is a station forcing, not
a calibrated 20 km mountain weather field. Station siting/history and terrain
representativeness remain separate checks.

The user-supplied `FireViewer_Die_Meteo_Horaire_2026.zip` contains a collector,
an interpolation adapter and tests, not observations. Its SHA-256 is
`be9260d865f7cf0f448c128545deaef83ee7e0ed9b68c99677ab712661cd835d`.
It requests Open-Meteo ECMWF IFS model archives. Keep that source marked
`estimated`, separate from station measurements. Do not call it a station
observation. The reviewed archive adapter needs corrections before reuse:

- scalar wind speed and interpolated ENU wind can disagree during a reversal;
- an exact timestamp unnecessarily depends on the next sample being present;
- all gusts are assigned to the preceding hour, although the
  [Open-Meteo parameter definition](https://open-meteo.com/en/docs/historical-weather-api)
  lists this IFS field at the indicated hour;
- the reference simulator period needs an additional final boundary sample;
- quality codes and explicit per-field provenance are absent from its input contract.

`HourlyWeatherTimeline` reads the normalized `fireviewer.weather-hourly.v1`
contract. It uses integer simulated microseconds, verifies the file checksum,
interpolates true east/north wind components, derives a consistent speed and
direction, and returns null for unavailable values. It does not rotate wind
into Lambert-93 grid axes: an engine adapter must supply and document that
rotation. It does not infer fuel moisture from soil moisture or relative humidity.

Supported temporal contracts are `sample`, `preceding_hour_sum`,
`preceding_hour_mean` and `preceding_hour_max`. Their exact interval convention
must be established for each source. The station descriptor alone describes
RR1 as an hourly amount without explicitly fixing the timestamp boundary.
Until that convention is independently verified, preserve RR1 as
`unverified_hourly_sum`; do not assign it to a continuous rain interval.
For Open-Meteo the documented preceding-hour rain sum can be distributed
uniformly within its hour, explicitly marked as an assumption. An hourly gust
maximum is context, not an instantaneous wind vector.

The production simulation adapter must put the selected weather sample,
source hashes, spatial model and interpolation policy into
`SimulationState.environment`. This module does not invent a propagation,
smoke or front API. It does not apply a source fallback automatically.

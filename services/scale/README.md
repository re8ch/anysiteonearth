# Scale v1.3

Scale scores known rural roads and discovers evidence-labelled field-edge,
riparian and forest-gap corridors using OSM, Sentinel-2, ESA WorldCover and
Copernicus DEM. It also proposes 8–25 km verified and exploratory scenic routes.
The Yangshi pilot remains a 10 m landscape analysis: candidates are always
`inferred_unverified` until GPS or human evidence supports them.

v1.2 also fuses Sentinel-1 RTC wetness time series, ERA5-Land/GPM antecedent
rainfall, GLO-30 hydrology derivatives and OSM access/obstacle tags. GPS traces
can verify roads, candidate corridors and loops; raw traces remain private by
default and results expose aggregate evidence only.

Optional source settings:

```env
SCALE_SENTINEL1_COLLECTION=sentinel-1-rtc
SCALE_ERA5_URL=https://archive-api.open-meteo.com/v1/archive
# Optional normalized/authenticated GPM gateway; empty means ERA5-Land only.
SCALE_GPM_URL=
SCALE_WEATHER_CACHE_TTL_HOURS=24
```

Weather values are regional evidence, not segment-scale measurements.

## Local run

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
SCALE_EMBEDDED_WORKER=true uvicorn scale.api:app --reload
```

The default in-memory repository is for development only. Production requires:

```bash
SCALE_DATABASE_URL=postgresql://... \
python -m scale.worker
```

Apply all files in `scale/migrations/` in numeric order before starting the API
and worker. In K3s, API and worker should use the internal PostgREST service to
avoid sending large GeoJSON layers through the public gateway.

## Yangshi request

```bash
curl -X POST http://localhost:8000/v1/analyses \
  -H 'content-type: application/json' \
  -d '{
    "bbox": {"west":111.705,"south":27.489,"east":111.947,"north":27.705},
    "activities":["hiking","gravel_bike","passenger_car","four_wheel_drive"],
    "products":["road_scores","candidate_corridors","scenic_loops"],
    "candidate_mode":"exploratory",
    "route_preferences":{"activities":["hiking","gravel_bike"],"min_distance_km":8,
      "max_distance_km":25,"max_slope":0.35,"allow_inferred":true},
    "time_window":{"start":"2026-01-01","end":"2026-07-20"}
  }'
```

Vector layers are available at
`/v1/analyses/{id}/layers/{roads|candidate_corridors|scenic_loops|places|contours|landcover}`.
Raster tiles use `/v1/analyses/{id}/tiles/{seasonal_spectral|satellite|landcover|terrain}/{season}/{z}/{x}/{y}.png`.

## Route digital twins

Scale compiles a completed 8–25 km scenic route into a durable asynchronous
trip twin. The backend samples Copernicus DEM, nearby OSM roads and semantic
layers, simulates wetness/drainage and atmosphere over trip time, then renders
separate aerial and follow-camera H.264 previews. The scene manifest preserves
field-level provenance so directly observed, inferred and simulated values stay
distinguishable.

```bash
curl -X POST http://localhost:8000/v1/twins \
  -H 'content-type: application/json' \
  -d '{"analysis_id":"ANALYSIS_UUID","route_id":"ROUTE_ID","scenario":"after_rain","camera_modes":["aerial","follow"],"export_1080p":true}'
```

Poll `/v1/twins/{id}`, fetch its manifest from `/v1/twins/{id}/result`, and
stream generated MP4 files through `/v1/twins/{id}/assets/{asset_name}`. API and
worker must share `SCALE_TWIN_ASSET_DIR`; the K3s manifest mounts the existing
cache PVC in both deployments. Apply `006_trip_twins.sql` before rollout.
Private GeoJSON LineString or GPX traces are submitted through `/v1/gps-traces`;
two independent supporting observers are required for `verified`.

Source limitations and acquisition failures are returned in result metadata;
the engine never substitutes generated imagery or invented spectral values.

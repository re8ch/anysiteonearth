# Scale v1.3 / RoveMap 4D route twin release

Release branch: `agent/scale-v1-1`  
Pilot area: Yangshi Town, Lianyuan, Loudi, Hunan  
Release date: 2026-07-22

## Delivered capabilities

- Asynchronous 8–25 km route-twin compilation backed by PostGIS jobs.
- Sentinel-2 cloud-masked seasonal RGB and spectral evidence.
- Sentinel-1 RTC wetness context, Copernicus DEM terrain and ESA WorldCover.
- OSM roads, buildings, settlements, waterways and transport obstacles.
- Procedural forest, farmland, water and village visualization with explicit
  `simulated_visualization` provenance.
- Clear, after-rain and mist scenarios with time-varying surface wetness,
  drainage risk and atmosphere.
- Aerial and follow-camera H.264 rendering at 720p, plus asynchronous 1080p
  exports.
- Spatial inspection that maps a video click to WGS84 and reports the closest
  observed or simulated semantic object.
- Scenic corridors, exploratory loops, private GPS evidence and verification.
- Mobile-first control hierarchy with mutually exclusive raster expressions and
  independently composable vector overlays.

## Runtime and reliability work

- Public API routed through the healthy regional edge.
- Shared twin assets stored on the Scale cache PVC.
- Backend deployment uses node-local incremental OCI imports and does not depend
  on the disabled Harbor registry.
- Sentinel-2 and Sentinel-1 remote COG reads use bounded overviews instead of
  full native-resolution AOI windows.
- Acquisition progress reports individual Sentinel scenes instead of appearing
  frozen at a coarse percentage.
- Analyses abandoned by a terminated worker are recovered through PostgREST
  lease cleanup; a database migration is retained for the eventual SQL-native
  queue lease.

## Verification snapshot

- Backend test suite: 38 passed.
- Next.js production build: passed, including type and lint checks.
- Production workload: two API replicas and one worker on
  `scale:1.3.1-20260722.5`.
- Recovered Yangshi analysis `1132f7fc-1d10-4aa9-970a-7bca795b277d` completed
  with 1,063 road segments and all seven result layers.
- Sentinel-2 acquisition for the near-limit AOI progressed through four visible
  scene heartbeats in roughly 75 seconds after optimization.
- Final 15.677 km pilot twin produced two 720p camera previews and two 1080p
  exports with 211 temporal keyframes.

## Fine-grained commit timeline

The implementation was intentionally split by concern. The principal sequence,
oldest first, is:

1. `9002be0` — compile backend route digital twins
2. `b8928e4` — add trip-twin playback and provenance
3. `6f7cb33` — deploy shared twin assets and document the API
4. `396de3e` — index twin geometry and reduce polling payloads
5. `54eacce` — render twins over satellite terrain
6. `39d6e71` — cloud-mask twin satellite mosaics
7. `2bba0da` — inspect provenance by video location
8. `b10a415` — route public API through a healthy regional edge
9. `9434704` — layer procedural landscape and OSM roads
10. `ba1cce9` — soften procedural landscape rendering
11. `92512da` — cache backdrops and synthesize villages
12. `7c75afc` — deploy cached twin backdrops
13. `dcc6132` — retain node-local image deployment
14. `d5bc980` — deploy the twin patch through incremental OCI
15. `506b1e9` — make weather scenarios visually distinct
16. `88df3e9` — deploy enhanced weather rendering
17. `29a4df4` — open shared trip twins by URL
18. `5c1beb4` — allow the shared preview origin
19. `18e8e79` — bound Sentinel-2 COG sampling and add queue recovery migration
20. `f64d958` — clarify analysis controls and layer hierarchy
21. `03fbf54` — recover stale analyses through PostgREST
22. `76e27fe` — deploy the responsive analysis pipeline
23. `2579eb2` — batch Sentinel-1 RTC overview reads
24. `2181462` — expose radar acquisition heartbeats
25. `932558b` — deploy bounded radar sampling

Earlier Scale v1.1/v1.2 commits cover candidate corridors, hydrology, contour
restoration, GPS verification and cache invalidation. User-owned untracked
`artifacts/` and `cloud-functions` paths are deliberately excluded from this
release.

ALTER TABLE scale.gps_traces DROP CONSTRAINT IF EXISTS gps_traces_target_type_check;
ALTER TABLE scale.gps_traces ADD CONSTRAINT gps_traces_target_type_check
  CHECK (target_type IN ('road_segment', 'candidate_corridor', 'scenic_loop'));

COMMENT ON TABLE scale.gps_traces IS
  'Private-by-default raw GPS observations; public API exposes aggregate evidence only.';

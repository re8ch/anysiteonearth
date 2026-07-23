ALTER TABLE scale.feedback ALTER COLUMN segment_id DROP NOT NULL;
ALTER TABLE scale.feedback ADD COLUMN IF NOT EXISTS target_type text NOT NULL DEFAULT 'road_segment';
ALTER TABLE scale.feedback ADD COLUMN IF NOT EXISTS target_id text;
UPDATE scale.feedback SET target_id = segment_id WHERE target_id IS NULL;
CREATE INDEX IF NOT EXISTS feedback_target_idx ON scale.feedback(analysis_id, target_type, target_id);

CREATE TABLE IF NOT EXISTS scale.gps_traces (
  id uuid PRIMARY KEY,
  analysis_id uuid NOT NULL REFERENCES scale.analyses(id) ON DELETE CASCADE,
  target_type text NOT NULL CHECK (target_type IN ('candidate_corridor', 'scenic_loop')),
  target_id text NOT NULL,
  geometry jsonb NOT NULL,
  observed_at timestamptz NOT NULL,
  observer_id text,
  visibility text NOT NULL CHECK (visibility IN ('private', 'public')) DEFAULT 'private',
  mean_distance_m double precision,
  coverage double precision NOT NULL DEFAULT 0,
  verification_state text NOT NULL CHECK (verification_state IN ('unmatched', 'gps_supported', 'verified')),
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gps_traces_target_idx
  ON scale.gps_traces(analysis_id, target_type, target_id) WHERE revoked_at IS NULL;

GRANT SELECT, INSERT, UPDATE ON scale.gps_traces TO anysite_app_rw;

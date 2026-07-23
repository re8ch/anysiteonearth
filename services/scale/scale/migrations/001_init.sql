CREATE SCHEMA IF NOT EXISTS scale;

CREATE TABLE IF NOT EXISTS scale.analyses (
  id uuid PRIMARY KEY,
  request jsonb NOT NULL,
  status text NOT NULL CHECK (status IN (
    'queued', 'acquiring', 'processing', 'inferencing', 'completed', 'failed'
  )),
  stage text NOT NULL,
  progress integer NOT NULL CHECK (progress BETWEEN 0 AND 100),
  error jsonb,
  result jsonb,
  aoi jsonb GENERATED ALWAYS AS (request->'bbox') STORED,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analyses_status_created_idx
  ON scale.analyses(status, created_at);
CREATE INDEX IF NOT EXISTS analyses_aoi_gin ON scale.analyses USING gin(aoi);

CREATE TABLE IF NOT EXISTS scale.feedback (
  id uuid PRIMARY KEY,
  analysis_id uuid NOT NULL REFERENCES scale.analyses(id) ON DELETE CASCADE,
  segment_id text NOT NULL,
  payload jsonb NOT NULL,
  visibility text NOT NULL CHECK (visibility IN ('private', 'public')),
  observed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scale.model_registry (
  version text PRIMARY KEY,
  production boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO scale.model_registry(version, production, metadata)
VALUES (
  'baseline_rules_v1',
  true,
  '{"kind":"rules","training_data_version":"cold_start_unlabelled","applicable_region":"Yangshi pilot","limitations":["Scores known OSM ways only","Sentinel-2 cannot resolve narrow trails","Not a navigation safety guarantee"]}'::jsonb
)
ON CONFLICT (version) DO NOTHING;

CREATE TABLE IF NOT EXISTS scale.trip_twins (
  id uuid PRIMARY KEY,
  analysis_id uuid NOT NULL REFERENCES scale.analyses(id) ON DELETE CASCADE,
  request jsonb NOT NULL,
  status text NOT NULL CHECK (status IN (
    'queued', 'acquiring', 'processing', 'inferencing', 'completed', 'failed'
  )),
  stage text NOT NULL,
  progress integer NOT NULL CHECK (progress BETWEEN 0 AND 100),
  error jsonb,
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS trip_twins_status_created_idx
  ON scale.trip_twins(status, created_at);

CREATE OR REPLACE FUNCTION scale.claim_trip_twin()
RETURNS SETOF scale.trip_twins
LANGUAGE sql
SECURITY DEFINER
SET search_path = scale, public
AS $$
  WITH candidate AS (
    SELECT id FROM scale.trip_twins
    WHERE status = 'queued' ORDER BY created_at
    FOR UPDATE SKIP LOCKED LIMIT 1
  )
  UPDATE scale.trip_twins t
  SET status='acquiring', stage='resolving_route', progress=5, updated_at=now()
  FROM candidate WHERE t.id=candidate.id RETURNING t.*;
$$;

GRANT SELECT, INSERT, UPDATE ON scale.trip_twins TO anysite_app_rw;
GRANT EXECUTE ON FUNCTION scale.claim_trip_twin() TO anysite_app_rw;

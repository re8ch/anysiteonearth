CREATE OR REPLACE FUNCTION scale.claim_analysis()
RETURNS SETOF scale.analyses
LANGUAGE sql
VOLATILE
AS $$
  WITH candidate AS (
    SELECT id
    FROM scale.analyses
    WHERE status = 'queued'
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  UPDATE scale.analyses AS analysis
  SET status = 'acquiring',
      stage = 'acquiring_sources',
      progress = 5,
      updated_at = now()
  FROM candidate
  WHERE analysis.id = candidate.id
  RETURNING analysis.*;
$$;

REVOKE ALL ON FUNCTION scale.claim_analysis() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION scale.claim_analysis() TO anysite_app_rw;

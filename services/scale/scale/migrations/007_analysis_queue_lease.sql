CREATE OR REPLACE FUNCTION scale.claim_analysis()
RETURNS SETOF scale.analyses
LANGUAGE sql
VOLATILE
AS $$
  WITH candidate AS (
    SELECT id
    FROM scale.analyses
    WHERE status = 'queued'
       OR (
         status IN ('acquiring', 'processing', 'inferencing')
         AND updated_at < now() - interval '15 minutes'
       )
    ORDER BY
      CASE WHEN status = 'queued' THEN 0 ELSE 1 END,
      created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  UPDATE scale.analyses AS analysis
  SET status = 'acquiring',
      stage = CASE
        WHEN analysis.status = 'queued' THEN 'acquiring_sources'
        ELSE 'recovering_interrupted_analysis'
      END,
      progress = CASE WHEN analysis.status = 'queued' THEN 5 ELSE analysis.progress END,
      updated_at = now()
  FROM candidate
  WHERE analysis.id = candidate.id
  RETURNING analysis.*;
$$;

REVOKE ALL ON FUNCTION scale.claim_analysis() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION scale.claim_analysis() TO anysite_app_rw;

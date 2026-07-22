CREATE TABLE IF NOT EXISTS scale.analysis_layers (
  analysis_id uuid NOT NULL REFERENCES scale.analyses(id) ON DELETE CASCADE,
  layer_name text NOT NULL,
  payload jsonb NOT NULL,
  feature_count integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (analysis_id, layer_name)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON scale.analysis_layers TO anysite_app_rw;

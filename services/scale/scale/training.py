"""Train the optional Yangshi LightGBM models once verified labels exist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FEATURES = [
    "grade_mean",
    "grade_max",
    "ruggedness",
    "ndvi",
    "ndwi",
    "bare_soil_index",
    "wetness_risk",
    "continuity_score",
]
TARGETS = [
    "hiking_label",
    "gravel_bike_label",
    "passenger_car_label",
    "four_wheel_drive_label",
]


def train(labels: Path, output: Path) -> None:
    try:
        import joblib
        import lightgbm as lgb
        import pandas as pd
        from sklearn.metrics import f1_score
    except ImportError as error:
        raise SystemExit("Install Scale with the ml extra before training") from error

    frame = pd.read_csv(labels)
    required = {"split", *FEATURES, *TARGETS}
    missing = required - set(frame.columns)
    if missing:
        raise SystemExit(f"Label file is missing columns: {sorted(missing)}")
    counts = frame["split"].value_counts().to_dict()
    if counts.get("train", 0) < 300 or counts.get("validation", 0) < 100 or counts.get("test", 0) < 100:
        raise SystemExit("Need at least 300 train, 100 validation, and 100 frozen test rows")

    output.mkdir(parents=True, exist_ok=True)
    metrics = {}
    for target in TARGETS:
        known = frame[target] != "unknown"
        train_rows = frame[(frame["split"] == "train") & known]
        test_rows = frame[(frame["split"] == "test") & known]
        model = lgb.LGBMClassifier(n_estimators=220, max_depth=6, learning_rate=0.04)
        model.fit(train_rows[FEATURES], train_rows[target])
        score = f1_score(test_rows[target], model.predict(test_rows[FEATURES]), average="macro")
        metrics[target] = score
        joblib.dump(model, output / f"{target}.joblib")
    metrics["production_eligible"] = min(metrics.values()) >= 0.70
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if not metrics["production_eligible"]:
        raise SystemExit("Frozen-test macro F1 is below 0.70; keep baseline_rules_v1 in production")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    train(arguments.labels, arguments.output)

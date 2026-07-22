from scale.verification import (
    gps_evidence_summary, independent_support_count, match_trace, recalculate_target,
    verification_state,
)


TARGET = {"type": "LineString", "coordinates": [[111.82, 27.59], [111.825, 27.59]]}


def result():
    return {"layers": {"candidate_corridors": {"type": "FeatureCollection", "features": [{
        "type": "Feature", "id": "candidate:1", "geometry": TARGET,
        "properties": {"confidence": 0.4, "verification_state": "inferred_unverified",
                       "observation_state": "inferred_unverified", "navigable": False},
    }]}}}


def test_gps_match_and_state_thresholds():
    distance, coverage = match_trace(
        {"type": "LineString", "coordinates": [[111.82, 27.59005], [111.825, 27.59005]]}, TARGET
    )
    assert distance < 20
    assert coverage >= 0.6
    assert verification_state(distance, coverage, 1) == "gps_supported"
    assert verification_state(distance, coverage, 2) == "verified"


def test_revoke_style_recalculation_downgrades_target():
    value = result()
    trace = {"mean_distance_m": 5, "coverage": 0.9, "geometry": TARGET, "observer_id": "one"}
    second = trace | {"observer_id": "two"}
    assert recalculate_target(value, "candidate_corridor", "candidate:1", [trace, second]) == "verified"
    assert recalculate_target(value, "candidate_corridor", "candidate:1", [trace]) == "gps_supported"
    assert recalculate_target(value, "candidate_corridor", "candidate:1", []) == "inferred_unverified"
    assert value["layers"]["candidate_corridors"]["features"][0]["properties"]["confidence"] == 0.4


def test_duplicate_anonymous_trace_is_not_independent_support():
    trace = {"mean_distance_m": 5, "coverage": 0.9, "geometry": TARGET}
    assert independent_support_count([trace, trace]) == 1


def test_gps_aggregate_exposes_evidence_not_raw_geometry():
    traces = [
        {"mean_distance_m": 5, "coverage": 0.9, "geometry": TARGET,
         "observer_id": "one", "observed_at": "2026-07-01T00:00:00Z"},
        {"mean_distance_m": 8, "coverage": 0.8, "geometry": TARGET,
         "observer_id": "two", "observed_at": "2026-07-02 00:00:00+00:00"},
    ]
    summary = gps_evidence_summary(traces)
    assert summary["independent_support_count"] == 2
    assert summary["mean_coverage"] == 0.85
    assert summary["first_observed_at"] == "2026-07-01T00:00:00+00:00"
    assert summary["last_observed_at"] == "2026-07-02T00:00:00+00:00"
    assert "geometry" not in summary
    value = result()
    recalculate_target(value, "candidate_corridor", "candidate:1", traces)
    props = value["layers"]["candidate_corridors"]["features"][0]["properties"]
    assert props["verification_state"] == "verified"
    assert props["evidence"][-1]["source"] == "private GPS trace aggregation"

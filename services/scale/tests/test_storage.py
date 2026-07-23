import respx
from httpx import Response
from uuid import uuid4

from scale.storage import PostgrestRepository


@respx.mock
def test_layer_upsert_retries_transient_gateway_errors(monkeypatch):
    repository = PostgrestRepository("https://db.example/scale", "secret", "app")
    route = respx.post("https://db.example/scale/analysis_layers").mock(
        side_effect=[Response(503), Response(502), Response(201)]
    )
    monkeypatch.setattr("scale.storage.time.sleep", lambda _: None)

    repository.save_layers(uuid4(), {"roads": {"type": "FeatureCollection", "features": []}})

    assert route.call_count == 3

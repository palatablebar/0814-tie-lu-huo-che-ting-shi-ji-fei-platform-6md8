import io
import json

from app.inputs import RATE_PROFILES


def test_correction_preview_does_not_write_db(client, clean):
    response = client.post(
        "/api/corrections/preview",
        data={"sample": "clean", "rate_profile": "corrected"},
    )
    assert response.status_code == 200
    body = response.json
    assert body["schedule"]["version"] == "2.0.0"
    assert body["balance"]["block_reasons"] == {"INVOICE_MISMATCH": 1}
    assert client.get("/api/runs").json == {"items": []}


def test_correction_run_is_persisted_separately(client, clean):
    legacy = client.post("/api/runs", data={"sample": "clean"})
    corrected = client.post(
        "/api/runs",
        data={"sample": "clean", "kind": "correction", "rate_profile": "corrected"},
    )
    assert legacy.status_code == corrected.status_code == 200
    assert legacy.json["id"] != corrected.json["id"]
    items = client.get("/api/runs").json["items"]
    assert len(items) == 2


def test_default_schedule_is_legacy_when_omitted(client, clean):
    response = client.post(
        "/api/runs", data={"sample": "clean", "kind": "correction"}
    )
    assert response.json["report"]["schedule"]["version"] == "1.0.0"


def test_unknown_rate_profile_is_rejected(client, clean):
    response = client.post(
        "/api/corrections/preview",
        data={"sample": "clean", "rate_profile": "nope"},
    )
    assert response.status_code == 422
    assert response.json["code"] == "RATE_PROFILE_UNKNOWN"


def test_malformed_rate_file_is_rejected(client, clean):
    response = client.post(
        "/api/corrections/preview",
        data={
            "sample": "clean",
            "rate_file": (io.BytesIO(b"{broken"), "rate.json"),
        },
    )
    assert response.status_code == 422
    assert response.json["code"] == "RATE_JSON_MALFORMED"


def test_structural_rate_error_returns_422(client, clean):
    payload = {"code": "X", "version": "1", "periods": []}
    response = client.post(
        "/api/corrections/preview",
        data={
            "sample": "clean",
            "rate_file": (io.BytesIO(json.dumps(payload).encode()), "rate.json"),
        },
    )
    assert response.status_code == 422
    assert response.json["code"] == "RATE_PERIODS_EMPTY"


def test_gapped_profile_blocks_but_is_accepted_as_input(client, clean):
    response = client.post(
        "/api/corrections/preview",
        data={"sample": "clean", "rate_profile": "gapped"},
    )
    assert response.status_code == 200
    assert response.json["balance"]["block_reasons"] == {"RATE_INTERVAL_MISSING": 1}


def test_correction_evidence_includes_schedule_and_lineage(client, clean):
    client.post("/api/runs", data={"sample": "clean"})
    run = client.post(
        "/api/runs",
        data={"sample": "clean", "kind": "correction", "rate_profile": "corrected"},
    ).json
    response = client.get(f"/api/runs/{run['id']}/evidence")
    assert response.status_code == 200
    packet = response.json
    assert packet["schema"] == "review-evidence/2"
    assert packet["schedule"]["fingerprint"] == RATE_PROFILES["corrected"]["fingerprint"]
    assert packet["lineage"]["prior_runs"][0]["deltas"]["0001"]["delta_cents"] == 80


def test_legacy_evidence_schema_unchanged(client, clean):
    run = client.post("/api/runs", data={"sample": "clean"}).json
    response = client.get(f"/api/runs/{run['id']}/evidence")
    assert response.json["schema"] == "review-evidence/1"
    assert "schedule" not in response.json


def test_releasable_correction_can_be_signed_end_to_end(client):
    run = client.post(
        "/api/runs",
        data={
            "sample": "corrected_ready",
            "kind": "correction",
            "rate_profile": "corrected",
        },
    ).json
    assert run["report"]["balance"]["releasable"] is True
    response = client.patch(
        f"/api/runs/{run['id']}",
        json={"revision": 0, "status": "APPROVED", "note": "月初更正账单核对无误"},
    )
    assert response.status_code == 200
    assert response.json["status"] == "APPROVED"
    # 已签发批次终结，再次复核被拒。
    forbidden = client.patch(
        f"/api/runs/{run['id']}",
        json={"revision": 1, "status": "HELD", "note": "试图撤销"},
    )
    assert forbidden.status_code == 409
    assert forbidden.json["code"] == "RUN_FINALIZED"

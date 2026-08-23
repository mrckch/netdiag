"""API-Tests über FastAPI TestClient (DB liegt via NETDIAG_DATA_DIR im Temp)."""
from fastapi.testclient import TestClient

from app.main import app, APP_VERSION

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == APP_VERSION


def test_floor_crud_and_conflict():
    r = client.post("/api/floors", json={"name": "Testetage-API"})
    assert r.status_code == 200
    fid = r.json()["id"]

    # Duplikat -> 409
    r = client.post("/api/floors", json={"name": "Testetage-API"})
    assert r.status_code == 409

    # Leerer Name -> 400
    r = client.post("/api/floors", json={"name": "  "})
    assert r.status_code == 400

    r = client.delete(f"/api/floors/{fid}")
    assert r.status_code == 200


def test_measurement_save_and_detail():
    result = {"link": {"speed": "1000Mb/s"}, "sniff": {}, "lldp": {}, "dhcp": {}}
    r = client.post("/api/measurements", json={"result": result, "kind": "autotest"})
    assert r.status_code == 200
    mid = r.json()["measurement_id"]

    r = client.get(f"/api/measurements/{mid}")
    assert r.status_code == 200
    assert r.json()["speed"] == "1000Mb/s"

    r = client.delete(f"/api/measurements/{mid}")
    assert r.status_code == 200

    r = client.get(f"/api/measurements/{mid}")
    assert r.status_code == 404


def test_measurement_without_result_rejected():
    r = client.post("/api/measurements", json={"kind": "autotest"})
    assert r.status_code == 400


def test_snmp_community_never_leaks():
    client.put("/api/settings", json={"snmp_community": "geheim123"})
    r = client.get("/api/settings")
    body = r.json()
    assert body["snmp_community"] == ""
    assert body["snmp_community_set"] == "1"
    assert "geheim123" not in r.text

    # Leeres Feld beim Speichern laesst den Wert unveraendert
    client.put("/api/settings", json={"snmp_community": ""})
    r = client.get("/api/settings")
    assert r.json()["snmp_community_set"] == "1"

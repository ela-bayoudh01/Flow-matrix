import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Flow


@pytest.fixture()
def client():
    # StaticPool : une connexion unique et partagée. Sans ça, chaque nouvelle connexion à
    # "sqlite:///:memory:" ouvre une base en mémoire DIFFÉRENTE et vide (piège classique) --
    # les requêtes de test et celles de l'app (via get_db) doivent voir la même base.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with Session(engine) as seed_session:
        seed_session.add(
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.10", dst_port=443,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                occurrence_count=3, allow_count=3, block_count=0, dominant_action="Allow",
                criticality_label="low",
            )
        )
        seed_session.commit()

    yield TestClient(app)

    app.dependency_overrides.clear()


def test_matrix_endpoint_returns_zone_cells_by_default(client):
    response = client.get("/api/matrix")

    assert response.status_code == 200
    body = response.json()
    assert body["dimension"] == "zone"
    assert body["cells"] == [
        {
            "row": "Users_Zone",
            "col": "Internet_Zone",
            "flow_count": 1,
            "allow_count": 3,
            "block_count": 0,
            "total_bytes": 0,
            "criticality_breakdown": {"low": 1},
        }
    ]


def test_matrix_endpoint_accepts_the_same_filters_as_flows_endpoint(client):
    matching = client.get("/api/matrix", params={"dominant_action": "Allow"})
    non_matching = client.get("/api/matrix", params={"dominant_action": "Block"})

    assert matching.status_code == 200
    assert len(matching.json()["cells"]) == 1
    assert non_matching.status_code == 200
    assert non_matching.json()["cells"] == []  # aucun Flow bloqué dans les données de seed


def test_matrix_endpoint_rejects_unknown_dimension(client):
    response = client.get("/api/matrix", params={"dimension": "nope"})

    assert response.status_code == 400


def test_flows_endpoint_supports_cell_drill_down_filters(client):
    response = client.get("/api/flows", params={"ingress_zone": "Users_Zone", "egress_zone": "Internet_Zone"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["src_ip"] == "10.10.1.1"
    assert body["summary"]["total_flows"] == 1


def test_validate_flow_updates_status(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    response = client.patch(
        f"/api/flows/{flow_id}/validation",
        json={"status": "approved", "validated_by": "Loulou"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validation_status"] == "approved"
    assert body["validated_by"] == "Loulou"
    assert body["validated_at"] is not None


def test_validate_flow_rejects_invalid_status(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    response = client.patch(f"/api/flows/{flow_id}/validation", json={"status": "maybe"})

    assert response.status_code == 400


def test_validate_flow_404_on_unknown_id(client):
    response = client.patch("/api/flows/999999/validation", json={"status": "approved"})

    assert response.status_code == 404


def test_validate_flow_records_a_history_entry_visible_via_the_api(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    client.patch(f"/api/flows/{flow_id}/validation", json={"status": "approved", "validated_by": "Loulou"})
    client.patch(f"/api/flows/{flow_id}/validation", json={"status": "blocked", "validated_by": "Encadrant"})

    response = client.get("/api/validation-history", params={"flow_id": flow_id})

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    # ordre : le plus récent en premier
    latest, first = body["items"]
    assert (latest["old_status"], latest["new_status"], latest["validated_by"]) == ("approved", "blocked", "Encadrant")
    assert (first["old_status"], first["new_status"], first["validated_by"]) == ("pending", "approved", "Loulou")
    assert latest["src_ip"] == "10.10.1.1"  # contexte du Flow inclus, pas besoin d'un 2e appel

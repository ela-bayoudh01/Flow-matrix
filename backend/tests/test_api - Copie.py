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

    test_client = TestClient(app)
    test_client.engine = engine  # exposé pour les tests qui doivent seeder des Flow additionnels
    yield test_client

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
            "total_duration_seconds": 0,
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


def test_run_qualification_endpoint_computes_criticality_for_unqualified_flows(client):
    # Flow sans criticality_label (comme un flow tout juste importé, jamais qualifié) --
    # doit être calculé par l'appel, pas laissé tel quel.
    with Session(client.engine) as session:
        session.add(
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.99", dst_ip="203.0.113.99", dst_port=445,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                occurrence_count=1, allow_count=1, block_count=0, dominant_action="Allow",
            )
        )
        session.commit()

    response = client.post("/api/flows/qualify")

    assert response.status_code == 200
    body = response.json()
    assert body["total_qualified"] == 2  # le flow seedé par le fixture + celui-ci
    assert sum(body["label_counts"].values()) == 2

    flows = client.get("/api/flows", params={"dst_port": 445}).json()["items"]
    assert flows[0]["criticality_label"] is not None  # port 445 (SMB) = sensible, jamais "non qualifié"


def _seed_permissive_rule_flows(client):
    # 12 Flow sous une même règle nommée, 12 dst_port distincts (> seuil de 10) -> déclenche
    # "trop_permissive" au prochain run.
    with Session(client.engine) as session:
        for port in range(1, 13):
            session.add(
                Flow(
                    source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.10", dst_port=port,
                    protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                    occurrence_count=1, allow_count=1, block_count=0, dominant_action="Allow",
                    criticality_label="low", last_access_control_rule_name="ACL_TEST_OUT",
                )
            )
        session.commit()


def test_run_recommendations_endpoint_detects_a_permissive_rule(client):
    _seed_permissive_rule_flows(client)

    response = client.post("/api/recommendations/run")

    assert response.status_code == 200
    body = response.json()
    assert body["findings_by_type"] == {"trop_permissive": 1}
    assert body["created"] == 1


def test_get_recommendations_lists_findings_after_a_run(client):
    _seed_permissive_rule_flows(client)
    client.post("/api/recommendations/run")

    response = client.get("/api/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["finding_type"] == "trop_permissive"
    assert body["items"][0]["status"] == "pending"


def test_get_recommendations_filters_by_status(client):
    _seed_permissive_rule_flows(client)
    client.post("/api/recommendations/run")

    pending = client.get("/api/recommendations", params={"status": "pending"})
    dismissed = client.get("/api/recommendations", params={"status": "dismissed"})

    assert pending.json()["total_count"] == 1
    assert dismissed.json()["total_count"] == 0


def test_review_recommendation_updates_status_and_reviewer(client):
    _seed_permissive_rule_flows(client)
    client.post("/api/recommendations/run")
    recommendation_id = client.get("/api/recommendations").json()["items"][0]["id"]

    response = client.patch(
        f"/api/recommendations/{recommendation_id}", json={"status": "dismissed", "reviewed_by": "Loulou"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "dismissed"
    assert body["reviewed_by"] == "Loulou"
    assert body["reviewed_at"] is not None


def test_review_recommendation_rejects_invalid_status(client):
    _seed_permissive_rule_flows(client)
    client.post("/api/recommendations/run")
    recommendation_id = client.get("/api/recommendations").json()["items"][0]["id"]

    response = client.patch(f"/api/recommendations/{recommendation_id}", json={"status": "maybe"})

    assert response.status_code == 400


def test_review_recommendation_404_on_unknown_id(client):
    response = client.patch("/api/recommendations/999999", json={"status": "dismissed"})

    assert response.status_code == 404


def test_rerunning_recommendations_preserves_a_reviewed_finding(client):
    _seed_permissive_rule_flows(client)
    client.post("/api/recommendations/run")
    recommendation_id = client.get("/api/recommendations").json()["items"][0]["id"]
    client.patch(f"/api/recommendations/{recommendation_id}", json={"status": "dismissed", "reviewed_by": "Loulou"})

    client.post("/api/recommendations/run")

    body = client.get("/api/recommendations").json()
    assert body["total_count"] == 1
    assert body["items"][0]["status"] == "dismissed"
    assert body["items"][0]["reviewed_by"] == "Loulou"


def _seed_approved_default_action_flow(client):
    with Session(client.engine) as session:
        session.add(
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="10.20.1.1", dst_port=445,
                protocol="tcp", ingress_zone="Interco_Zone", egress_zone="ESCALE_DCS_ZONE",
                last_access_control_rule_name="Default Action",
                validation_status="approved", validated_by="Loulou",
            )
        )
        session.commit()


def test_run_acl_proposals_endpoint_creates_a_proposal_from_an_approved_flow(client):
    _seed_approved_default_action_flow(client)

    response = client.post("/api/acl-proposals/run")

    assert response.status_code == 200
    body = response.json()
    assert body["by_intent"] == {"create": 1, "tighten": 0, "revoke": 0}
    assert body["created"] == 1


def test_get_acl_proposals_lists_proposals_after_a_run(client):
    _seed_approved_default_action_flow(client)
    client.post("/api/acl-proposals/run")

    response = client.get("/api/acl-proposals")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["intent"] == "create"
    assert body["items"][0]["status"] == "pending"


def test_get_acl_proposals_filters_by_intent(client):
    _seed_approved_default_action_flow(client)
    client.post("/api/acl-proposals/run")

    create_only = client.get("/api/acl-proposals", params={"intent": "create"})
    tighten_only = client.get("/api/acl-proposals", params={"intent": "tighten"})

    assert create_only.json()["total_count"] == 1
    assert tighten_only.json()["total_count"] == 0


def test_review_acl_proposal_updates_status_and_validator(client):
    _seed_approved_default_action_flow(client)
    client.post("/api/acl-proposals/run")
    proposal_id = client.get("/api/acl-proposals").json()["items"][0]["id"]

    response = client.patch(f"/api/acl-proposals/{proposal_id}", json={"status": "approved", "validated_by": "Encadrant"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["validated_by"] == "Encadrant"
    assert body["validated_at"] is not None


def test_review_acl_proposal_rejects_invalid_status(client):
    _seed_approved_default_action_flow(client)
    client.post("/api/acl-proposals/run")
    proposal_id = client.get("/api/acl-proposals").json()["items"][0]["id"]

    response = client.patch(f"/api/acl-proposals/{proposal_id}", json={"status": "maybe"})

    assert response.status_code == 400


def test_review_acl_proposal_404_on_unknown_id(client):
    response = client.patch("/api/acl-proposals/999999", json={"status": "approved"})

    assert response.status_code == 404


def test_rerunning_acl_proposals_preserves_a_reviewed_proposal(client):
    _seed_approved_default_action_flow(client)
    client.post("/api/acl-proposals/run")
    proposal_id = client.get("/api/acl-proposals").json()["items"][0]["id"]
    client.patch(f"/api/acl-proposals/{proposal_id}", json={"status": "approved", "validated_by": "Encadrant"})

    client.post("/api/acl-proposals/run")

    body = client.get("/api/acl-proposals").json()
    assert body["total_count"] == 1
    assert body["items"][0]["status"] == "approved"
    assert body["items"][0]["validated_by"] == "Encadrant"


def test_review_acl_proposal_records_a_history_entry_visible_via_the_api(client):
    _seed_approved_default_action_flow(client)
    client.post("/api/acl-proposals/run")
    proposal_id = client.get("/api/acl-proposals").json()["items"][0]["id"]

    client.patch(f"/api/acl-proposals/{proposal_id}", json={"status": "approved", "validated_by": "Loulou"})
    client.patch(f"/api/acl-proposals/{proposal_id}", json={"status": "rejected", "validated_by": "Encadrant"})

    response = client.get("/api/acl-proposal-history", params={"acl_proposal_id": proposal_id})

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    latest, first = body["items"]
    assert (latest["old_status"], latest["new_status"], latest["changed_by"]) == ("approved", "rejected", "Encadrant")
    assert (first["old_status"], first["new_status"], first["changed_by"]) == ("pending", "approved", "Loulou")


def test_create_manual_acl_proposal(client):
    response = client.post(
        "/api/acl-proposals",
        json={
            "source": "SITE-A-FWTEST",
            "ingress_zone": "Users_Zone",
            "egress_zone": "Servers_Zone",
            "protocol": "tcp",
            "dst_port": 8443,
            "src_networks": ["10.5.1.50"],
            "dst_networks": ["10.20.1.99"],
            "proposed_action": "Allow",
            "justification": "Nouveau serveur pas encore observé dans les logs.",
            "created_by": "Loulou",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["intent"] == "manual"
    assert body["status"] == "pending"
    assert body["source_recommendation_id"] is None
    assert "Nouveau serveur" in body["proposed_rule_text"]


def test_create_manual_acl_proposal_rejects_an_exact_duplicate(client):
    payload = {
        "source": "SITE-A-FWTEST", "ingress_zone": "Users_Zone", "egress_zone": "Servers_Zone",
        "protocol": "tcp", "dst_port": 8443, "proposed_action": "Allow", "justification": "Test.",
    }
    first = client.post("/api/acl-proposals", json=payload)
    second = client.post("/api/acl-proposals", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


def test_manual_acl_proposal_appears_in_the_list_alongside_generated_ones(client):
    _seed_approved_default_action_flow(client)
    client.post("/api/acl-proposals/run")
    client.post(
        "/api/acl-proposals",
        json={"proposed_action": "Allow", "justification": "Test.", "ingress_zone": "X", "egress_zone": "Y"},
    )

    body = client.get("/api/acl-proposals").json()

    assert body["total_count"] == 2
    assert {item["intent"] for item in body["items"]} == {"create", "manual"}

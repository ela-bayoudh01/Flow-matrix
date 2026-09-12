from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Flow, ImportLog, LogEntry

from .sample_logs import ALLOW_HTTPS_LINE, BLOCK_SMB_LINE, SITE_B_ALLOW_LINE


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
                # cycle_* mirrorent le lifetime -- situation réelle avant toute clôture
                # (flow_engine.consolidate() incrémente les deux ensemble). build_matrix()
                # agrège désormais sur cycle_* (2026-09-12, correction du bug lifetime/cycle) :
                # sans ce miroir, ce Flow serait exclu de /api/matrix (cycle_occurrence_count
                # resterait à 0 par défaut).
                cycle_occurrence_count=3, cycle_allow_count=3, cycle_block_count=0, cycle_dominant_action="Allow",
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


def test_flow_log_entries_endpoint_lists_underlying_connections(client):
    # Drill-down (2026-09-06, demande de l'encadrant) : occurrence_count agrège des LogEntry
    # jamais consultables un par un jusqu'ici.
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    with Session(client.engine) as session:
        session.add_all(
            [
                LogEntry(
                    source="SITE-A-FWTEST", raw_line="ligne 1", flow_id=flow_id,
                    first_packet_at=datetime(2026, 8, 1, 10, 0), access_control_rule_action="Allow",
                    initiator_bytes=100, responder_bytes=200,
                ),
                LogEntry(
                    source="SITE-A-FWTEST", raw_line="ligne 2", flow_id=flow_id,
                    first_packet_at=datetime(2026, 8, 2, 10, 0), access_control_rule_action="Allow",
                    initiator_bytes=150, responder_bytes=250,
                ),
            ]
        )
        session.commit()

    response = client.get(f"/api/flows/{flow_id}/log-entries")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    # Le plus récent en premier (même convention que l'Historique des validations).
    assert body["items"][0]["initiator_bytes"] == 150
    assert body["items"][1]["initiator_bytes"] == 100


def test_flow_log_entries_endpoint_paginates(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    with Session(client.engine) as session:
        session.add_all(
            [
                LogEntry(source="SITE-A-FWTEST", raw_line="x", flow_id=flow_id, first_packet_at=datetime(2026, 8, i))
                for i in range(1, 6)
            ]
        )
        session.commit()

    response = client.get(f"/api/flows/{flow_id}/log-entries", params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 5
    assert len(body["items"]) == 2


def test_flow_log_entries_endpoint_404_on_unknown_flow(client):
    response = client.get("/api/flows/999999/log-entries")

    assert response.status_code == 404


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


def test_validate_flow_never_requires_justification_even_when_contradicting_observed_action(client):
    # Valider/Bloquer classique reste toujours immédiat (décision de conception 2026-09-05) --
    # même "blocked" sur un flow dominant_action="Allow" (seedé) ne demande jamais de
    # justification. Seul "Changer la règle" (change_flow_rule) le fait.
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    response = client.patch(f"/api/flows/{flow_id}/validation", json={"status": "blocked", "validated_by": "Loulou"})

    assert response.status_code == 200
    body = response.json()
    assert body["validation_status"] == "blocked"
    assert body["decided_action"] is None


def test_change_flow_rule_requires_justification(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    response = client.patch(
        f"/api/flows/{flow_id}/change-rule", json={"target_action": "Block", "validated_by": "Loulou"}
    )

    assert response.status_code == 400
    assert "justification" in response.json()["detail"].lower()


def test_change_flow_rule_with_justification_sets_decided_action(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    response = client.patch(
        f"/api/flows/{flow_id}/change-rule",
        json={"target_action": "Block", "validated_by": "Loulou", "justification": "Comportement suspect."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validation_status"] == "blocked"
    assert body["decided_action"] == "Block"


def test_change_flow_rule_rejects_invalid_target_action(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    response = client.patch(
        f"/api/flows/{flow_id}/change-rule", json={"target_action": "Maybe", "justification": "Test."}
    )

    assert response.status_code == 400


def test_change_flow_rule_404_on_unknown_id(client):
    response = client.patch(
        "/api/flows/999999/change-rule", json={"target_action": "Block", "justification": "Test."}
    )

    assert response.status_code == 404


def test_action_change_fiche_pdf_for_a_rule_change(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    client.patch(
        f"/api/flows/{flow_id}/change-rule",
        json={"target_action": "Block", "validated_by": "Loulou", "justification": "Comportement suspect."},
    )
    history_id = client.get("/api/validation-history", params={"flow_id": flow_id}).json()["items"][0]["id"]

    response = client.get(f"/api/validation-history/{history_id}/fiche.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_action_change_fiche_pdf_404_for_a_classic_validation_history_entry(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    client.patch(f"/api/flows/{flow_id}/validation", json={"status": "approved"})  # pas un changement de règle
    history_id = client.get("/api/validation-history", params={"flow_id": flow_id}).json()["items"][0]["id"]

    response = client.get(f"/api/validation-history/{history_id}/fiche.pdf")

    assert response.status_code == 404


def test_action_change_fiche_pdf_404_on_unknown_history_id(client):
    response = client.get("/api/validation-history/999999/fiche.pdf")

    assert response.status_code == 404


def test_validate_flow_records_a_history_entry_visible_via_the_api(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    client.patch(f"/api/flows/{flow_id}/validation", json={"status": "approved", "validated_by": "Loulou"})
    client.patch(
        f"/api/flows/{flow_id}/change-rule",
        json={"target_action": "Block", "validated_by": "Encadrant", "justification": "Trafic suspect confirmé."},
    )

    response = client.get("/api/validation-history", params={"flow_id": flow_id})

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    # ordre : le plus récent en premier
    latest, first = body["items"]
    assert (latest["old_status"], latest["new_status"], latest["validated_by"]) == ("approved", "blocked", "Encadrant")
    assert (first["old_status"], first["new_status"], first["validated_by"]) == ("pending", "approved", "Loulou")
    # "Changer la règle" (Allow -> Block) : justification/action-avant/action-décidée figées ;
    # la 1ère entrée (Valider classique) n'en porte aucune.
    assert latest["justification"] == "Trafic suspect confirmé."
    assert latest["observed_action_before"] == "Allow"
    assert latest["decided_action"] == "Block"
    assert first["justification"] is None
    assert latest["src_ip"] == "10.10.1.1"  # contexte du Flow inclus, pas besoin d'un 2e appel


def test_validation_history_supports_keyword_search(client):
    # Demande de l'encadrant (2026-08-25) : recherche par mot-clé sur le contexte Flow
    # (src/dst/source) autant que sur l'historique lui-même (old/new_status, validated_by).
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    client.patch(f"/api/flows/{flow_id}/validation", json={"status": "approved", "validated_by": "Loulou"})

    by_ip = client.get("/api/validation-history", params={"q": "10.10.1.1"})
    by_validator = client.get("/api/validation-history", params={"q": "Loulou"})
    no_match = client.get("/api/validation-history", params={"q": "nope-nothing-matches"})

    assert by_ip.json()["total_count"] == 1
    assert by_validator.json()["total_count"] == 1
    assert no_match.json()["total_count"] == 0


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


def test_get_recommendations_supports_keyword_search(client):
    # Demande de l'encadrant (2026-08-25) : recherche par mot-clé sur rule_name/zones/source.
    _seed_permissive_rule_flows(client)
    client.post("/api/recommendations/run")

    match = client.get("/api/recommendations", params={"q": "ACL_TEST_OUT"})
    no_match = client.get("/api/recommendations", params={"q": "nope-nothing-matches"})

    assert match.json()["total_count"] == 1
    assert no_match.json()["total_count"] == 0


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


def test_get_acl_proposals_supports_keyword_search(client):
    # Demande de l'encadrant (2026-08-25) : recherche par mot-clé sur zones/source/intent.
    _seed_approved_default_action_flow(client)
    client.post("/api/acl-proposals/run")

    match = client.get("/api/acl-proposals", params={"q": "Interco_Zone"})
    no_match = client.get("/api/acl-proposals", params={"q": "nope-nothing-matches"})

    assert match.json()["total_count"] == 1
    assert no_match.json()["total_count"] == 0


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


def test_validation_cycle_diff_without_a_cycle_flags_the_seeded_flow_as_nouveau(client):
    response = client.get("/api/validation-cycles/diff")

    assert response.status_code == 200
    body = response.json()
    assert body["cycles"] == {}
    assert body["total_count"] == 1
    assert body["items"][0]["diff_status"] == "nouveau"
    assert body["summary"] == {
        "nouveau": 1, "disparu": 0, "regle_non_appliquee": 0, "modifie": 0, "conforme": 0, "pending_review_count": 1,
    }


def test_close_validation_cycle_requires_a_source(client):
    response = client.post("/api/validation-cycles/close")

    assert response.status_code == 422  # source est un paramètre requis, pas de cycle global


def test_close_validation_cycle_then_a_new_import_reveals_the_four_statuses(client):
    # Cycle 1 : clôture de la baseline (simule la validation de l'encadrant), pour la source
    # du flux seedé par le fixture.
    close = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST", "closed_by": "encadrant"})
    assert close.status_code == 200
    assert close.json()["flow_count"] == 1
    assert close.json()["closed_by"] == "encadrant"
    assert close.json()["source"] == "SITE-A-FWTEST"

    seeded_flow_id = client.get("/api/flows").json()["items"][0]["id"]

    with Session(client.engine) as session:
        seeded = session.get(Flow, seeded_flow_id)
        seeded.last_seen_at = None  # jamais revu depuis la baseline -> "disparu"

        # Nouveau flux -- apparu après la baseline.
        session.add(
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.50", dst_ip="203.0.113.50", dst_port=445,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                occurrence_count=1, dominant_action="Block",
            )
        )
        session.commit()

    diff = client.get("/api/validation-cycles/diff")
    assert diff.status_code == 200
    body = diff.json()
    assert body["cycles"]["SITE-A-FWTEST"]["closed_by"] == "encadrant"
    statuses = {item["flow"]["src_ip"]: item["diff_status"] for item in body["items"]}
    assert statuses == {"10.10.1.1": "disparu", "10.10.1.50": "nouveau"}
    assert body["summary"]["disparu"] == 1
    assert body["summary"]["nouveau"] == 1
    # "disparu" est informationnel -- jamais compté comme écart à traiter (2026-08-21).
    assert body["summary"]["pending_review_count"] == 1  # seul le "nouveau" (encore pending)

    # Filtre diff_status : ne montre que les écarts demandés.
    only_nouveau = client.get("/api/validation-cycles/diff", params={"diff_status": "nouveau"})
    assert only_nouveau.json()["total_count"] == 1
    assert only_nouveau.json()["items"][0]["flow"]["src_ip"] == "10.10.1.50"


def test_regle_non_appliquee_when_decided_action_still_not_observed(client):
    # Scénario complet de l'encadrant (2026-09-03) : le responsable décide Block sur un flux
    # Allow, clôture le cycle, mais le log suivant montre que le pare-feu n'a pas changé --
    # doit ressortir "regle_non_appliquee", jamais noyé dans "modifie".
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    with Session(client.engine) as session:
        session.get(Flow, flow_id).last_seen_at = datetime(2026, 8, 1)
        session.commit()

    client.patch(
        f"/api/flows/{flow_id}/change-rule",
        json={"target_action": "Block", "validated_by": "Loulou", "justification": "Trafic à bloquer."},
    )
    close = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"})
    assert close.status_code == 200

    # "Nouveau log" : le flux est revu, mais l'action de ce cycle reste Allow -- la règle
    # Block décidée n'a probablement pas encore été intégrée dans FMC. cycle_dominant_action
    # réaffirmé à la main (close_cycle() vient de le remettre à None) : un vrai réimport le
    # recalculerait via flow_engine.consolidate() depuis les nouvelles occurrences.
    with Session(client.engine) as session:
        flow = session.get(Flow, flow_id)
        flow.last_seen_at = datetime(2026, 8, 15)
        flow.cycle_dominant_action = "Allow"
        flow.cycle_allow_count = 1
        session.commit()

    diff = client.get("/api/validation-cycles/diff")
    body = diff.json()
    assert body["items"][0]["diff_status"] == "regle_non_appliquee"
    assert body["items"][0]["diff_details"] == {"decided_action": {"avant": "Block", "apres": "Allow"}}
    assert body["summary"]["regle_non_appliquee"] == 1
    assert body["summary"]["modifie"] == 0


def test_validation_cycle_never_mixes_two_sources(client):
    # Clôturer le cycle de SITE-A-FWTEST ne doit jamais affecter la baseline (encore
    # inexistante) de SITE-B-FWTEST -- écart trouvé après démo à l'encadrant (2026-08-21).
    with Session(client.engine) as session:
        session.add(
            Flow(
                source="SITE-B-FWTEST", src_ip="10.20.1.1", dst_ip="203.0.113.99", dst_port=443,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                occurrence_count=1, dominant_action="Allow",
            )
        )
        session.commit()

    client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"})

    diff = client.get("/api/validation-cycles/diff")
    body = diff.json()
    statuses = {item["flow"]["src_ip"]: item["diff_status"] for item in body["items"]}
    assert statuses["10.20.1.1"] == "nouveau"  # SITE-B-FWTEST n'a pas de baseline
    assert set(body["cycles"].keys()) == {"SITE-A-FWTEST"}


def test_validation_cycle_diff_rejects_unknown_diff_status(client):
    response = client.get("/api/validation-cycles/diff", params={"diff_status": "nope"})

    assert response.status_code == 400


def test_validation_cycle_diff_supports_keyword_search(client):
    # Demande de l'encadrant (2026-08-25) : même mécanisme que Table des flux.
    match = client.get("/api/validation-cycles/diff", params={"q": "10.10.1.1"})
    no_match = client.get("/api/validation-cycles/diff", params={"q": "nope-nothing-matches"})

    assert match.json()["total_count"] == 1
    assert no_match.json()["total_count"] == 0


def test_validation_cycle_cell_diff_matches_the_zone_dimension(client):
    seeded_flow_id = client.get("/api/flows").json()["items"][0]["id"]
    with Session(client.engine) as session:
        session.get(Flow, seeded_flow_id).last_seen_at = datetime(2026, 8, 1)
        session.commit()

    client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"})

    with Session(client.engine) as session:
        # Revu depuis la baseline, rien de structurant ne change -> "conforme". cycle_*
        # réaffirmés explicitement (2026-09-12) : close_cycle() vient de les remettre à
        # zéro/None, un vrai réimport (flow_engine.consolidate()) les recalculerait en
        # retrouvant "Allow" -- même principe déjà appliqué dans test_validation_cycle_engine.py.
        seeded_flow = session.get(Flow, seeded_flow_id)
        seeded_flow.last_seen_at = datetime(2026, 8, 15)
        seeded_flow.cycle_dominant_action = "Allow"
        seeded_flow.cycle_occurrence_count = 1
        seeded_flow.cycle_allow_count = 1
        session.add(
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.50", dst_ip="203.0.113.50", dst_port=445,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                occurrence_count=1, dominant_action="Block",
                cycle_occurrence_count=1, cycle_block_count=1, cycle_dominant_action="Block",
            )
        )
        session.commit()

    response = client.get("/api/validation-cycles/cell-diff", params={"dimension": "zone"})

    assert response.status_code == 200
    body = response.json()
    assert body["cells"] == [
        {
            "row": "Users_Zone",
            "col": "Internet_Zone",
            "diff_summary": {"nouveau": 1, "disparu": 0, "regle_non_appliquee": 0, "modifie": 0, "conforme": 1},
        }
    ]


def test_validation_cycle_cell_diff_rejects_unknown_dimension(client):
    response = client.get("/api/validation-cycles/cell-diff", params={"dimension": "nope"})

    assert response.status_code == 400


def test_list_validation_cycles_returns_past_cycles_most_recent_first(client):
    client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST", "note": "premier"})
    client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST", "note": "second"})

    response = client.get("/api/validation-cycles")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert [item["note"] for item in body["items"]] == ["second", "premier"]


def test_list_validation_cycles_filters_by_source(client):
    client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"})
    with Session(client.engine) as session:
        session.add(
            Flow(
                source="SITE-B-FWTEST", src_ip="10.20.1.1", dst_ip="203.0.113.99", dst_port=443,
                protocol="tcp", occurrence_count=1, dominant_action="Allow",
            )
        )
        session.commit()
    client.post("/api/validation-cycles/close", params={"source": "SITE-B-FWTEST"})

    response = client.get("/api/validation-cycles", params={"source": "SITE-B-FWTEST"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["source"] == "SITE-B-FWTEST"


def test_validated_matrix_endpoint_without_a_cycle_returns_empty(client):
    response = client.get("/api/validation-cycles/matrix", params={"source": "SITE-A-FWTEST"})

    assert response.status_code == 200
    body = response.json()
    assert body["cycle"] is None
    assert body["cells"] == []


def test_validated_matrix_endpoint_reflects_the_frozen_state_not_live_flows(client):
    client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"})
    seeded_flow_id = client.get("/api/flows").json()["items"][0]["id"]

    with Session(client.engine) as session:
        session.get(Flow, seeded_flow_id).ingress_zone = "Interco_Zone"  # ne doit pas apparaître
        session.commit()

    response = client.get("/api/validation-cycles/matrix", params={"source": "SITE-A-FWTEST", "dimension": "zone"})

    assert response.status_code == 200
    body = response.json()
    assert body["cycle"]["source"] == "SITE-A-FWTEST"
    assert body["cells"] == [
        {
            "row": "Users_Zone", "col": "Internet_Zone", "flow_count": 1,
            "allow_count": 3, "block_count": 0, "total_bytes": 0, "total_duration_seconds": 0,
            "criticality_breakdown": {"low": 1},
        }
    ]


def test_validated_matrix_endpoint_rejects_timeslot_zone(client):
    client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"})

    response = client.get("/api/validation-cycles/matrix", params={"source": "SITE-A-FWTEST", "dimension": "timeslot_zone"})

    assert response.status_code == 400


def test_validated_matrix_flows_endpoint_lists_the_cell_and_reflects_frozen_state(client):
    # Drill-down d'une cellule de la Matrice Validée (2026-09-09, demande de l'encadrant) --
    # doit refléter l'état figé du cycle, jamais l'état courant du Flow.
    cycle = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"}).json()
    seeded_flow_id = client.get("/api/flows").json()["items"][0]["id"]

    with Session(client.engine) as session:
        session.get(Flow, seeded_flow_id).criticality_label = "critical"  # ne doit pas apparaître
        session.commit()

    response = client.get(
        "/api/validation-cycles/matrix/flows",
        params={"cycle_id": cycle["id"], "dimension": "zone", "row_value": "Users_Zone", "col_value": "Internet_Zone"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["criticality_label"] == "low"  # figé, pas "critical"
    assert body["items"][0]["validated_by"] is None  # jamais figé -- honnête, pas fabriqué


def test_validated_matrix_flows_endpoint_404_on_unknown_cycle(client):
    response = client.get(
        "/api/validation-cycles/matrix/flows",
        params={"cycle_id": 999999, "dimension": "zone", "row_value": "x", "col_value": "y"},
    )

    assert response.status_code == 404


def test_validated_matrix_flows_endpoint_rejects_timeslot_zone(client):
    cycle = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"}).json()

    response = client.get(
        "/api/validation-cycles/matrix/flows",
        params={"cycle_id": cycle["id"], "dimension": "timeslot_zone", "row_value": "x", "col_value": "y"},
    )

    assert response.status_code == 400


def _make_flow_regle_non_appliquee(client, flow_id):
    """Même scénario que test_regle_non_appliquee_when_decided_action_still_not_observed --
    décide Block sur le flow seedé (Allow), clôture un cycle, puis "réimporte" en gardant
    l'observé Allow. Retourne le cycle clôturé (dict JSON)."""
    with Session(client.engine) as session:
        session.get(Flow, flow_id).last_seen_at = datetime(2026, 8, 1)
        session.commit()

    client.patch(
        f"/api/flows/{flow_id}/change-rule",
        json={"target_action": "Block", "validated_by": "Loulou", "justification": "Trafic a bloquer."},
    )
    cycle = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"}).json()

    with Session(client.engine) as session:
        flow = session.get(Flow, flow_id)
        flow.last_seen_at = datetime(2026, 8, 15)
        flow.cycle_dominant_action = "Allow"
        flow.cycle_allow_count = 1
        session.commit()

    return cycle


def test_cycle_report_endpoint_returns_pdf_with_decisions(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    client.patch(
        f"/api/flows/{flow_id}/change-rule",
        json={"target_action": "Block", "validated_by": "Loulou", "justification": "A bloquer."},
    )
    cycle = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"}).json()

    response = client.get(f"/api/validation-cycles/{cycle['id']}/report.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_cycle_report_endpoint_returns_pdf_even_when_no_decisions_made(client):
    cycle = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"}).json()

    response = client.get(f"/api/validation-cycles/{cycle['id']}/report.pdf")

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_cycle_report_endpoint_404_on_unknown_cycle(client):
    response = client.get("/api/validation-cycles/999999/report.pdf")

    assert response.status_code == 404


def test_rule_enforcement_claim_endpoint_rejects_a_flow_not_currently_regle_non_appliquee(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    response = client.post(f"/api/flows/{flow_id}/rule-enforcement-claims")

    assert response.status_code == 400


def test_get_rule_enforcement_claim_endpoint_is_null_before_any_diff_computed(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]

    response = client.get(f"/api/flows/{flow_id}/rule-enforcement-claim")

    assert response.status_code == 200
    assert response.json() is None


def test_rule_enforcement_claim_endpoint_creates_and_increments(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    _make_flow_regle_non_appliquee(client, flow_id)
    client.get("/api/validation-cycles/diff")  # déclenche la détection passive

    first = client.post(f"/api/flows/{flow_id}/rule-enforcement-claims")
    assert first.status_code == 200
    body = first.json()
    assert body["claim_count"] == 1
    assert body["last_claimed_at"] is not None
    assert body["first_detected_at"] is not None

    second = client.post(f"/api/flows/{flow_id}/rule-enforcement-claims")
    assert second.json()["claim_count"] == 2
    # first_detected_at ne change jamais après coup.
    assert second.json()["first_detected_at"] == body["first_detected_at"]

    fetched = client.get(f"/api/flows/{flow_id}/rule-enforcement-claim")
    assert fetched.json()["claim_count"] == 2


def test_rule_enforcement_claim_fiche_endpoint_returns_pdf(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    _make_flow_regle_non_appliquee(client, flow_id)
    client.get("/api/validation-cycles/diff")
    claim_id = client.post(f"/api/flows/{flow_id}/rule-enforcement-claims").json()["id"]

    response = client.get(f"/api/rule-enforcement-claims/{claim_id}/fiche.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_rule_enforcement_claim_fiche_endpoint_404_on_unknown_claim(client):
    response = client.get("/api/rule-enforcement-claims/999999/fiche.pdf")

    assert response.status_code == 404


def test_validation_cycle_diff_sums_regle_non_appliquee_across_sources_for_dashboard_tile(client):
    flow_id = client.get("/api/flows").json()["items"][0]["id"]
    _make_flow_regle_non_appliquee(client, flow_id)

    response = client.get("/api/validation-cycles/diff")  # aucun filtre source

    assert response.status_code == 200
    assert response.json()["summary"]["regle_non_appliquee"] == 1


def test_run_acl_proposals_scoped_to_a_cycle_only_considers_flows_approved_since_the_previous_one(client):
    # Flux approuvé AVANT le premier cycle -- doit être considéré au premier cycle (pas
    # d'historique précédent = équivalent à l'ancien comportement global pour cette source).
    _seed_approved_default_action_flow(client)
    cycle_1 = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"}).json()

    run_1 = client.post("/api/acl-proposals/run", params={"cycle_id": cycle_1["id"]})
    assert run_1.status_code == 200
    assert run_1.json()["by_intent"]["create"] == 1

    # Un 2e flux approuvé après le cycle 1 (validated_at postérieur à sa clôture, comme le
    # ferait vraiment apply_validation()), MÊME groupe zone/protocole/port que le premier
    # (même identité de proposition ACL) -- seul lui doit être considéré "nouveau" pour le
    # cycle 2, mais la proposition existante (générée au cycle 1) ne doit JAMAIS perdre le
    # premier flux au passage (cf. fusion des flows dans _upsert_proposals, pas un
    # remplacement -- régression réelle identifiée en concevant le scoping par cycle).
    validated_after_cycle_1 = datetime.fromisoformat(cycle_1["closed_at"]) + timedelta(seconds=1)
    with Session(client.engine) as session:
        session.add(
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.77", dst_ip="10.20.1.77", dst_port=445,
                protocol="tcp", ingress_zone="Interco_Zone", egress_zone="ESCALE_DCS_ZONE",
                occurrence_count=1, dominant_action="Allow",
                last_access_control_rule_name="Default Action",
                validation_status="approved", validated_at=validated_after_cycle_1,
            )
        )
        session.commit()

    cycle_2 = client.post("/api/validation-cycles/close", params={"source": "SITE-A-FWTEST"}).json()
    run_2 = client.post("/api/acl-proposals/run", params={"cycle_id": cycle_2["id"]})
    assert run_2.status_code == 200
    assert run_2.json()["by_intent"]["create"] == 1  # seul le nouveau flux considéré "nouveau" pour ce cycle

    proposals = client.get("/api/acl-proposals").json()["items"]
    create_proposals = [p for p in proposals if p["intent"] == "create"]
    assert len(create_proposals) == 1  # même groupe zone/protocole/port -> une seule proposition, jamais dupliquée
    all_flow_ids = set(create_proposals[0]["rationale"]["flow_ids"])
    # Les deux flux (approuvés à des cycles différents) doivent être couverts par CETTE
    # proposition -- le premier n'a jamais disparu au 2e passage.
    assert len(all_flow_ids) == 2


def test_run_acl_proposals_unknown_cycle_returns_404(client):
    response = client.post("/api/acl-proposals/run", params={"cycle_id": 999})

    assert response.status_code == 404


# --- Politiques de sous-réseau (2026-09-10) -- fonctionnalité isolée -----------------------


def test_observed_subnets_endpoint_groups_the_seeded_flow(client):
    # Le flow seedé est 10.10.1.1 (SITE-A-FWTEST) -- doit apparaître dans son /24.
    response = client.get("/api/network-policies/subnets", params={"source": "SITE-A-FWTEST"})

    assert response.status_code == 200
    body = response.json()
    assert body["prefix_length"] == 24
    assert body["items"] == [{"cidr": "10.10.1.0/24", "machine_count": 1, "flow_count": 1}]


def test_observed_subnets_endpoint_respects_prefix_length_param(client):
    response = client.get(
        "/api/network-policies/subnets", params={"source": "SITE-A-FWTEST", "prefix_length": 28}
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["cidr"] == "10.10.1.0/28"


def test_observed_subnets_endpoint_rejects_out_of_range_prefix_length(client):
    response = client.get(
        "/api/network-policies/subnets", params={"source": "SITE-A-FWTEST", "prefix_length": 99}
    )

    assert response.status_code == 400


def test_create_network_policy_endpoint_persists_and_returns_it(client):
    response = client.post(
        "/api/network-policies",
        json={
            "source": "SITE-A-FWTEST", "src_cidr": "10.10.1.0/24", "destination": "Internet_Zone",
            "protocol": "tcp", "dst_port": 443, "action": "Block",
            "justification": "Isoler ce sous-reseau.", "decided_by": "Loulou",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] is not None
    assert body["src_cidr"] == "10.10.1.0/24"
    assert body["action"] == "Block"


def test_create_network_policy_endpoint_requires_justification(client):
    response = client.post(
        "/api/network-policies",
        json={"src_cidr": "10.10.1.0/24", "destination": "Internet_Zone", "action": "Block", "justification": "  "},
    )

    assert response.status_code == 400


def test_create_network_policy_endpoint_rejects_invalid_action(client):
    response = client.post(
        "/api/network-policies",
        json={"src_cidr": "10.10.1.0/24", "destination": "Internet_Zone", "action": "Maybe", "justification": "Test."},
    )

    assert response.status_code == 400


def test_list_network_policies_endpoint_returns_created_policies(client):
    client.post(
        "/api/network-policies",
        json={"src_cidr": "10.10.1.0/24", "destination": "Internet_Zone", "action": "Block", "justification": "Test."},
    )

    response = client.get("/api/network-policies")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["src_cidr"] == "10.10.1.0/24"


def test_network_policy_fiche_endpoint_returns_pdf(client):
    policy_id = client.post(
        "/api/network-policies",
        json={"src_cidr": "10.10.1.0/24", "destination": "Internet_Zone", "action": "Block", "justification": "Test."},
    ).json()["id"]

    response = client.get(f"/api/network-policies/{policy_id}/fiche.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_network_policy_fiche_endpoint_404_on_unknown_policy(client):
    response = client.get("/api/network-policies/999999/fiche.pdf")

    assert response.status_code == 404


def test_network_policies_never_touch_flow_decided_action(client):
    # Vérification explicite de l'isolation demandée : créer une politique ne doit JAMAIS
    # toucher au Flow existant (decided_action, validation_status...).
    flow_before = client.get("/api/flows").json()["items"][0]

    client.post(
        "/api/network-policies",
        json={
            "source": "SITE-A-FWTEST", "src_cidr": "10.10.1.0/24", "destination": "Internet_Zone",
            "action": "Block", "justification": "Test isolation.",
        },
    )

    flow_after = client.get("/api/flows").json()["items"][0]
    assert flow_after["decided_action"] == flow_before["decided_action"]
    assert flow_after["validation_status"] == flow_before["validation_status"]


# --- Fusion "Politiques de sous-réseau" -> Cycle de validation (2026-09-11) -----------------


def test_validation_cycle_diff_endpoint_respects_src_cidr(client):
    # Le flow seedé est 10.10.1.1 (SITE-A-FWTEST) -- doit apparaître avec un src_cidr englobant,
    # disparaître avec un src_cidr qui ne l'englobe pas.
    matching = client.get("/api/validation-cycles/diff", params={"src_cidr": "10.10.1.0/24"})
    non_matching = client.get("/api/validation-cycles/diff", params={"src_cidr": "10.20.0.0/24"})

    assert matching.status_code == 200
    assert matching.json()["total_count"] == 1
    assert non_matching.status_code == 200
    assert non_matching.json()["total_count"] == 0


def test_validation_cycle_diff_endpoint_rejects_an_invalid_src_cidr(client):
    response = client.get("/api/validation-cycles/diff", params={"src_cidr": "not-a-cidr"})

    assert response.status_code == 400


def test_validation_cycle_subnet_diff_endpoint_groups_the_seeded_flow_with_its_diff_status(client):
    response = client.get("/api/validation-cycles/subnet-diff", params={"source": "SITE-A-FWTEST"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "SITE-A-FWTEST"
    assert body["prefix_length"] == 24
    assert body["cycle"] is None  # aucune baseline pour l'instant
    assert body["items"] == [
        {
            "cidr": "10.10.1.0/24",
            "machine_count": 1,
            "flow_count": 1,
            "diff_summary": {"nouveau": 1, "disparu": 0, "regle_non_appliquee": 0, "modifie": 0, "conforme": 0},
        }
    ]


def test_validation_cycle_subnet_diff_endpoint_respects_prefix_length_param(client):
    response = client.get(
        "/api/validation-cycles/subnet-diff", params={"source": "SITE-A-FWTEST", "prefix_length": 28}
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["cidr"] == "10.10.1.0/28"


def test_validation_cycle_subnet_diff_endpoint_rejects_out_of_range_prefix_length(client):
    response = client.get(
        "/api/validation-cycles/subnet-diff", params={"source": "SITE-A-FWTEST", "prefix_length": 99}
    )

    assert response.status_code == 400


def test_validation_cycle_subnet_diff_endpoint_unknown_source_returns_empty_items(client):
    response = client.get("/api/validation-cycles/subnet-diff", params={"source": "NOPE"})

    assert response.status_code == 200
    assert response.json()["items"] == []


# --- Historique des imports (2026-09-11, demande de l'encadrant) ---------------------------


def test_import_endpoint_records_an_import_log_entry(client):
    content = (ALLOW_HTTPS_LINE + "\n" + SITE_B_ALLOW_LINE + "\n").encode("utf-8")

    response = client.post("/api/logs/import", files={"file": ("real_import.log", content, "text/plain")})

    assert response.status_code == 200
    summary = response.json()

    with Session(client.engine) as session:
        log = session.query(ImportLog).one()
        assert log.filename == "real_import.log"
        assert log.source == "SITE-A-FWTEST, SITE-B-FWTEST"
        assert log.lines_read == summary["lines_read"]
        assert log.log_entries_created == summary["log_entries_created"]
        assert log.flows_touched == summary["flows_touched"]


def test_import_logs_endpoint_lists_most_recent_first(client):
    client.post("/api/logs/import", files={"file": ("first.log", ALLOW_HTTPS_LINE.encode("utf-8"), "text/plain")})
    client.post("/api/logs/import", files={"file": ("second.log", BLOCK_SMB_LINE.encode("utf-8"), "text/plain")})

    response = client.get("/api/import-logs")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert [item["filename"] for item in body["items"]] == ["second.log", "first.log"]


def test_import_logs_endpoint_empty_returns_empty_list(client):
    response = client.get("/api/import-logs")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total_count": 0}

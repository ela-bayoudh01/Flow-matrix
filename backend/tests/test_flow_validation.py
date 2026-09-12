import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.flow_validation import apply_rule_change, apply_validation
from app.models import Flow, FlowValidationHistory, RuleEnforcementClaim


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_apply_validation_updates_flow_and_records_history(session):
    flow = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    session.add(flow)
    session.commit()
    assert flow.validation_status == "pending"

    apply_validation(session, flow, "approved", "Loulou")

    assert flow.validation_status == "approved"
    assert flow.validated_by == "Loulou"
    assert flow.validated_at is not None

    history = session.query(FlowValidationHistory).filter_by(flow_id=flow.id).one()
    assert history.old_status == "pending"
    assert history.new_status == "approved"
    assert history.validated_by == "Loulou"


def test_two_successive_validations_produce_two_history_entries_in_order(session):
    flow = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    session.add(flow)
    session.commit()

    apply_validation(session, flow, "approved", "Loulou")
    apply_validation(session, flow, "blocked", "Encadrant")

    history = flow.validation_history
    assert len(history) == 2
    assert (history[0].old_status, history[0].new_status) == ("pending", "approved")
    assert (history[1].old_status, history[1].new_status) == ("approved", "blocked")
    assert history[1].validated_by == "Encadrant"


def test_apply_validation_never_sets_decided_action_or_justification(session):
    # Valider/Bloquer classique -- même contredisant l'action observée, ça reste un simple
    # clic immédiat (décision de conception 2026-09-05) : jamais de justification, jamais de
    # decided_action. Seul apply_rule_change ("Changer la règle") peut les fixer.
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443,
        protocol="tcp", dominant_action="Allow",
    )
    session.add(flow)
    session.commit()

    apply_validation(session, flow, "blocked", "Loulou")

    assert flow.decided_action is None
    history = session.query(FlowValidationHistory).filter_by(flow_id=flow.id).one()
    assert history.justification is None
    assert history.observed_action_before is None
    assert history.decided_action is None


# --- apply_rule_change ("Changer la règle", 2026-09-05) ------------------------------------


def test_apply_rule_change_sets_decided_action_and_freezes_history(session):
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443,
        protocol="tcp", dominant_action="Allow",
    )
    session.add(flow)
    session.commit()

    apply_rule_change(session, flow, "Block", "Loulou", "Trafic suspect confirmé.")

    assert flow.decided_action == "Block"
    assert flow.validation_status == "blocked"
    history = session.query(FlowValidationHistory).filter_by(flow_id=flow.id).one()
    assert history.justification == "Trafic suspect confirmé."
    assert history.observed_action_before == "Allow"
    assert history.decided_action == "Block"


def test_apply_rule_change_target_allow_sets_status_approved(session):
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443,
        protocol="tcp", dominant_action="Block",
    )
    session.add(flow)
    session.commit()

    apply_rule_change(session, flow, "Allow", "Loulou", "Faux positif, à autoriser.")

    assert flow.decided_action == "Allow"
    assert flow.validation_status == "approved"


def test_apply_rule_change_decided_action_persists_across_a_later_classic_validation(session):
    # Une decided_action reste active tant qu'aucun nouveau "Changer la règle" ne la
    # remplace -- un Valider/Bloquer classique ultérieur ne doit jamais l'effacer silencieusement.
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443,
        protocol="tcp", dominant_action="Allow",
    )
    session.add(flow)
    session.commit()
    apply_rule_change(session, flow, "Block", "Loulou", "Trafic suspect confirmé.")
    assert flow.decided_action == "Block"

    apply_validation(session, flow, "approved", "Loulou")

    assert flow.decided_action == "Block"


def test_apply_rule_change_clears_a_stale_rule_enforcement_claim(session):
    # Une réclamation "Règle non appliquée" en cours portait sur l'ANCIENNE decided_action --
    # plus valide dès qu'une nouvelle décision la remplace (2026-09-10).
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443,
        protocol="tcp", dominant_action="Allow",
    )
    session.add(flow)
    session.commit()
    session.add(RuleEnforcementClaim(flow_id=flow.id, claim_count=3))
    session.commit()

    apply_rule_change(session, flow, "Block", "Loulou", "Nouvelle decision, ancienne reclamation obsolete.")

    assert session.query(RuleEnforcementClaim).filter_by(flow_id=flow.id).count() == 0

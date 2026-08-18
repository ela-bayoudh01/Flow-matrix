import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AclProposal, Flow, RuleRecommendation
from app.Services import acl_engine


@pytest.fixture()
def session():
    db_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(db_engine)
    with Session(db_engine) as session:
        yield session


def make_flow(session, **overrides):
    defaults = dict(
        source="SITE-A-FWTEST",
        src_ip="10.10.1.1",
        dst_ip="10.20.1.1",
        dst_port=445,
        protocol="tcp",
        ingress_zone="Interco_Zone",
        egress_zone="ESCALE_DCS_ZONE",
        last_access_control_rule_name="Default Action",
        validation_status="approved",
        validated_by="Loulou",
    )
    defaults.update(overrides)
    flow = Flow(**defaults)
    session.add(flow)
    return flow


# --- "create" --------------------------------------------------------------------------


def test_create_proposal_for_an_approved_flow_under_default_action(session):
    make_flow(session)
    session.commit()

    summary = acl_engine.run(session)

    assert summary["by_intent"] == {"create": 1, "tighten": 0, "revoke": 0}
    proposal = session.query(AclProposal).one()
    assert proposal.intent == "create"
    assert proposal.source == "SITE-A-FWTEST"
    assert proposal.ingress_zone == "Interco_Zone"
    assert proposal.egress_zone == "ESCALE_DCS_ZONE"
    assert proposal.protocol == "tcp"
    assert proposal.dst_port == 445
    assert proposal.proposed_action == "Allow"
    assert proposal.status == "pending"
    assert proposal.src_networks == {"observed": ["10.10.1.1"], "count": 1, "truncated": False}
    assert "CREATE_" in proposal.suggested_rule_name
    assert "Loulou" in proposal.proposed_rule_text


def test_create_groups_several_flows_sharing_the_same_shape(session):
    make_flow(session, src_ip="10.10.1.1", dst_ip="10.20.1.1")
    make_flow(session, src_ip="10.10.1.2", dst_ip="10.20.1.1")
    session.commit()

    acl_engine.run(session)

    proposal = session.query(AclProposal).one()
    assert proposal.src_networks["count"] == 2
    assert set(proposal.rationale["flow_ids"]) == {f.id for f in session.query(Flow).all()}


def test_create_ignores_pending_flows(session):
    make_flow(session, validation_status="pending")
    session.commit()

    summary = acl_engine.run(session)

    assert summary["total_proposals"] == 0


def test_create_ignores_flows_already_covered_by_a_named_rule(session):
    make_flow(session, last_access_control_rule_name="ACL_ANY_INTERNET_HTTPS_OUT")
    session.commit()

    summary = acl_engine.run(session)

    assert summary["total_proposals"] == 0


def test_create_links_to_a_matching_sans_regle_explicite_recommendation(session):
    make_flow(session)
    recommendation = RuleRecommendation(
        source="SITE-A-FWTEST", finding_type="sans_regle_explicite", rule_name="Default Action",
        ingress_zone="Interco_Zone", egress_zone="ESCALE_DCS_ZONE", flow_count=1,
    )
    session.add(recommendation)
    session.commit()

    acl_engine.run(session)

    proposal = session.query(AclProposal).one()
    assert proposal.source_recommendation_id == recommendation.id
    assert proposal.rationale["source_recommendation_id"] == recommendation.id


def test_create_truncates_network_enumeration_beyond_the_cap(session):
    for i in range(acl_engine.NETWORK_ENUMERATION_CAP + 5):
        make_flow(session, src_ip=f"10.10.1.{i}", dst_ip="10.20.1.1")
    session.commit()

    acl_engine.run(session)

    proposal = session.query(AclProposal).one()
    assert proposal.src_networks["truncated"] is True
    assert proposal.src_networks["count"] == acl_engine.NETWORK_ENUMERATION_CAP + 5
    assert len(proposal.src_networks["observed"]) == 10  # échantillon, pas la liste complète


def test_never_mixes_two_sources_into_one_create_proposal(session):
    make_flow(session, source="SITE-A-FWTEST", src_ip="10.10.1.1")
    make_flow(session, source="SITE-B-FWTEST", src_ip="10.10.1.1")
    session.commit()

    acl_engine.run(session)

    proposals = session.query(AclProposal).all()
    assert len(proposals) == 2
    assert {p.source for p in proposals} == {"SITE-A-FWTEST", "SITE-B-FWTEST"}


# --- "tighten" / "revoke" ----------------------------------------------------------------


def test_tighten_proposal_for_an_acknowledged_trop_permissive_recommendation(session):
    recommendation = RuleRecommendation(
        source="SITE-A-FWTEST", finding_type="trop_permissive", rule_name="ACL_ANY_INTERNET_HTTPS_OUT",
        status="acknowledged", evidence={"triggers": {"distinct_dst_port_over_threshold": True}},
    )
    session.add(recommendation)
    session.commit()

    summary = acl_engine.run(session)

    assert summary["by_intent"] == {"create": 0, "tighten": 1, "revoke": 0}
    proposal = session.query(AclProposal).one()
    assert proposal.intent == "tighten"
    assert proposal.target_rule_name == "ACL_ANY_INTERNET_HTTPS_OUT"
    assert proposal.proposed_action == "Allow"
    assert proposal.source_recommendation_id == recommendation.id
    assert "distinct_dst_port_over_threshold" in proposal.proposed_rule_text


def test_tighten_ignores_pending_recommendations(session):
    session.add(
        RuleRecommendation(source="SITE-A-FWTEST", finding_type="trop_permissive", rule_name="ACL_X", status="pending")
    )
    session.commit()

    summary = acl_engine.run(session)

    assert summary["total_proposals"] == 0


def test_revoke_proposal_for_an_acknowledged_obsolete_recommendation(session):
    recommendation = RuleRecommendation(
        source="SITE-A-FWTEST", finding_type="obsolete", rule_name="ACL_OLD_RULE",
        status="acknowledged", evidence={"inactivity_days": 42},
    )
    session.add(recommendation)
    session.commit()

    summary = acl_engine.run(session)

    assert summary["by_intent"] == {"create": 0, "tighten": 0, "revoke": 1}
    proposal = session.query(AclProposal).one()
    assert proposal.intent == "revoke"
    assert proposal.target_rule_name == "ACL_OLD_RULE"
    assert proposal.proposed_action == "Remove"


# --- Idempotence -----------------------------------------------------------------------


def test_rerunning_does_not_duplicate_proposals(session):
    make_flow(session)
    session.commit()

    first = acl_engine.run(session)
    second = acl_engine.run(session)

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["updated"] == 1
    assert session.query(AclProposal).count() == 1


def test_rerunning_preserves_a_human_review(session):
    make_flow(session)
    session.commit()
    acl_engine.run(session)

    proposal = session.query(AclProposal).one()
    proposal.status = "approved"
    proposal.validated_by = "Encadrant"
    session.commit()

    acl_engine.run(session)

    proposal = session.query(AclProposal).one()
    assert proposal.status == "approved"
    assert proposal.validated_by == "Encadrant"


# --- "manual" : ajout direct, pas de Flow ni de RuleRecommendation d'origine ---------------


def test_build_manual_proposal_for_a_not_yet_observed_flow(session):
    proposal = acl_engine.build_manual_proposal(
        source="SITE-A-FWTEST", ingress_zone="Users_Zone", egress_zone="Servers_Zone",
        protocol="tcp", dst_port=8443, src_ips=["10.5.1.50"], dst_ips=["10.20.1.99"],
        proposed_action="Allow", suggested_rule_name=None, target_rule_name=None,
        justification="Nouveau serveur prévu pour le déploiement X, mise en service le 2026-09-01.",
        created_by="Loulou",
    )
    session.add(proposal)
    session.commit()

    assert proposal.intent == "manual"
    assert proposal.status == "pending"
    assert proposal.source_recommendation_id is None
    assert proposal.flows == []  # aucun Flow d'origine, contrairement à "create"
    assert proposal.rationale == {
        "trigger": "manual_entry",
        "note": "Nouveau serveur prévu pour le déploiement X, mise en service le 2026-09-01.",
        "created_by": "Loulou",
    }
    assert "MANUAL_" in proposal.suggested_rule_name
    assert "déploiement X" in proposal.proposed_rule_text


def test_build_manual_proposal_defaults_unset_zones(session):
    proposal = acl_engine.build_manual_proposal(
        source="SITE-A-FWTEST", ingress_zone=None, egress_zone=None,
        protocol=None, dst_port=None, src_ips=[], dst_ips=[],
        proposed_action="Allow", suggested_rule_name="MY_CUSTOM_NAME", target_rule_name=None,
        justification="Test.", created_by=None,
    )

    from app.models import ZONE_UNSET, RULE_NAME_UNSET

    assert proposal.ingress_zone == ZONE_UNSET
    assert proposal.egress_zone == ZONE_UNSET
    assert proposal.target_rule_name == RULE_NAME_UNSET
    assert proposal.suggested_rule_name == "MY_CUSTOM_NAME"  # respecte le nom fourni

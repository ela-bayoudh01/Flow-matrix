from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Flow, RuleRecommendation
from app.Services import recommendation_engine as engine

BASE = datetime(2026, 1, 1, 0, 0, 0)


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
        dst_ip="203.0.113.10",
        dst_port=443,
        protocol="tcp",
        ingress_zone="Users_Zone",
        egress_zone="Internet_Zone",
        occurrence_count=1,
        allow_count=1,
        block_count=0,
        dominant_action="Allow",
        criticality_label="low",
        last_access_control_rule_name="ACL_TEST_OUT",
        first_seen_at=BASE,
        last_seen_at=BASE,
    )
    defaults.update(overrides)
    flow = Flow(**defaults)
    session.add(flow)
    return flow


# --- trop_permissive ---------------------------------------------------------------------


def test_flags_trop_permissive_on_distinct_dst_port_over_threshold(session):
    for port in range(1, 13):  # 12 ports distincts > seuil (10)
        make_flow(session, dst_ip=f"203.0.113.{port}", dst_port=port)
    session.commit()

    summary = engine.run(session)

    assert summary["findings_by_type"] == {engine.FINDING_TROP_PERMISSIVE: 1}
    finding = session.query(RuleRecommendation).one()
    assert finding.finding_type == engine.FINDING_TROP_PERMISSIVE
    assert finding.rule_name == "ACL_TEST_OUT"
    assert finding.evidence["triggers"]["distinct_dst_port_over_threshold"] is True
    assert finding.evidence["distinct_dst_port"] == 12


def test_flags_trop_permissive_on_high_or_critical_flow(session):
    make_flow(session, criticality_label="high")
    session.commit()

    summary = engine.run(session)

    assert summary["findings_by_type"] == {engine.FINDING_TROP_PERMISSIVE: 1}
    finding = session.query(RuleRecommendation).one()
    assert finding.evidence["triggers"]["high_or_critical_present"] is True
    assert finding.evidence["high_or_critical_flow_count"] == 1


def test_flags_trop_permissive_on_sensitive_port(session):
    make_flow(session, dst_port=445)  # SMB, dans SENSITIVE_PORTS du Qualification Engine
    session.commit()

    summary = engine.run(session)

    assert summary["findings_by_type"] == {engine.FINDING_TROP_PERMISSIVE: 1}
    finding = session.query(RuleRecommendation).one()
    assert finding.evidence["triggers"]["sensitive_port_present"] is True
    assert finding.evidence["sensitive_ports_observed"] == [445]


def test_does_not_flag_a_clean_narrow_rule(session):
    # Règle étroite, criticité basse, port courant -- aucun signal, aucun finding.
    for i in range(3):
        make_flow(session, dst_ip=f"203.0.113.{i}")
    session.commit()

    summary = engine.run(session)

    assert summary["total_findings"] == 0
    assert session.query(RuleRecommendation).count() == 0


def test_never_mixes_two_sources_into_one_finding(session):
    for port in range(1, 13):
        make_flow(session, source="SITE-A-FWTEST", dst_ip=f"203.0.113.{port}", dst_port=port)
    for port in range(1, 13):
        make_flow(session, source="SITE-B-FWTEST", dst_ip=f"198.51.100.{port}", dst_port=port)
    session.commit()

    engine.run(session)

    findings = session.query(RuleRecommendation).all()
    assert len(findings) == 2
    assert {f.source for f in findings} == {"SITE-A-FWTEST", "SITE-B-FWTEST"}
    for f in findings:
        assert f.flow_count == 12  # jamais le total des deux sources mélangées


# --- sans_regle_explicite (Default Action) ------------------------------------------------


def test_flags_default_action_grouped_by_zone_pair_with_block_only_note(session):
    make_flow(
        session,
        last_access_control_rule_name="Default Action",
        allow_count=0,
        block_count=5,
        dominant_action="Block",
        criticality_label="medium",
    )
    session.commit()

    summary = engine.run(session)

    assert summary["findings_by_type"] == {engine.FINDING_SANS_REGLE_EXPLICITE: 1}
    finding = session.query(RuleRecommendation).one()
    assert finding.rule_name == "Default Action"
    assert (finding.ingress_zone, finding.egress_zone) == ("Users_Zone", "Internet_Zone")
    assert finding.evidence["allow_count"] == 0
    assert finding.evidence["block_count"] == 5
    assert "pas de risque actif" in finding.evidence["note"]


def test_default_action_note_warns_when_traffic_is_allowed(session):
    make_flow(
        session,
        last_access_control_rule_name="Default Action",
        allow_count=2,
        block_count=0,
        dominant_action="Allow",
    )
    session.commit()

    engine.run(session)

    finding = session.query(RuleRecommendation).one()
    assert finding.evidence["allow_count"] == 2
    assert "à traiter en priorité" in finding.evidence["note"]


def test_flow_without_rule_name_is_excluded_not_crashed(session):
    make_flow(session, last_access_control_rule_name=None)
    session.commit()

    summary = engine.run(session)

    assert summary["total_findings"] == 0


# --- obsolete (avec garde sur la fenêtre d'observation) ------------------------------------


def test_obsolete_detection_disabled_on_a_short_observation_window(session):
    make_flow(session, first_seen_at=BASE, last_seen_at=BASE)
    make_flow(session, dst_ip="203.0.113.99", first_seen_at=BASE + timedelta(days=1), last_seen_at=BASE + timedelta(days=2))
    session.commit()

    summary = engine.run(session)

    assert summary["obsolete_detection_enabled"] is False
    assert summary["findings_by_type"].get(engine.FINDING_OBSOLETE) is None


def test_obsolete_detection_fires_on_a_long_enough_window_with_stale_rule(session):
    # Fenêtre totale > MIN_OBSERVATION_WINDOW_DAYS, une règle inactive depuis > OBSOLETE_INACTIVITY_DAYS.
    make_flow(
        session,
        last_access_control_rule_name="ACL_OLD_RULE",
        first_seen_at=BASE,
        last_seen_at=BASE,
    )
    make_flow(
        session,
        dst_ip="203.0.113.99",
        last_access_control_rule_name="ACL_RECENT_RULE",
        first_seen_at=BASE,
        last_seen_at=BASE + timedelta(days=40),
    )
    session.commit()

    summary = engine.run(session)

    assert summary["obsolete_detection_enabled"] is True
    assert summary["findings_by_type"][engine.FINDING_OBSOLETE] == 1
    finding = session.query(RuleRecommendation).filter_by(finding_type=engine.FINDING_OBSOLETE).one()
    assert finding.rule_name == "ACL_OLD_RULE"
    assert finding.evidence["inactivity_days"] == 40.0


# --- idempotence -----------------------------------------------------------------------


def test_rerunning_the_engine_does_not_duplicate_findings(session):
    for port in range(1, 13):
        make_flow(session, dst_ip=f"203.0.113.{port}", dst_port=port)
    session.commit()

    first = engine.run(session)
    second = engine.run(session)

    assert first["created"] == 1
    assert second["created"] == 0
    assert second["updated"] == 1
    assert session.query(RuleRecommendation).count() == 1


def test_rerunning_the_engine_preserves_a_human_review(session):
    for port in range(1, 13):
        make_flow(session, dst_ip=f"203.0.113.{port}", dst_port=port)
    session.commit()
    engine.run(session)

    finding = session.query(RuleRecommendation).one()
    finding.status = "dismissed"
    finding.reviewed_by = "Loulou"
    session.commit()

    engine.run(session)

    finding = session.query(RuleRecommendation).one()
    assert finding.status == "dismissed"
    assert finding.reviewed_by == "Loulou"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Flow
from app.Services import qualification_engine as qe


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_external_to_internal_sensitive_port_rare_allow_is_critical():
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="203.0.113.1", dst_ip="10.10.1.1", dst_port=445,
        protocol="tcp", ingress_zone="Internet_Zone", egress_zone="Users_Zone",
        occurrence_count=1, dominant_action="Allow", validation_status="pending",
    )

    result = qe.qualify(flow)

    assert result["qualification_reasons"]["zone"]["category"] == "externe_vers_interne"
    assert result["qualification_reasons"]["port"]["category"] == "port_sensible"
    assert result["qualification_reasons"]["frequency"]["category"] == "rare"
    assert result["qualification_reasons"]["action"]["points"] == 10
    # 40 + 30 + 15 + 10 = 95
    assert result["criticality_score"] == 95.0
    assert result["criticality_label"] == "critical"
    assert result["security_status"] == "at_risk"  # pending + high/critical


def test_frequency_is_ignored_when_zone_and_port_are_both_baseline():
    # Itération 2 (2026-08-12) : une simple navigation web rare (1 seule visite) ne doit
    # plus, à elle seule, faire basculer un flow interne->externe/port courant en "medium".
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", dst_port=443,
        protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
        occurrence_count=1, dominant_action="Allow", validation_status="pending",
    )

    result = qe.qualify(flow)

    assert result["qualification_reasons"]["frequency"]["category"] == "ignoree_sans_signal_zone_ou_port"
    assert result["qualification_reasons"]["frequency"]["points"] == 0
    # 5 (interne->externe) + 0 (port courant) + 0 (fréquence ignorée) + 10 (Allow) = 15
    assert result["criticality_score"] == 15.0
    assert result["criticality_label"] == "low"


def test_frequency_still_counts_when_zone_already_shows_a_signal():
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="10.10.2.1", dst_port=443,
        protocol="tcp", ingress_zone="Users_Zone", egress_zone="Servers_Zone",  # interne->interne
        occurrence_count=1, dominant_action="Allow", validation_status="pending",
    )

    result = qe.qualify(flow)

    assert result["qualification_reasons"]["frequency"]["category"] == "rare"
    assert result["qualification_reasons"]["frequency"]["points"] == qe.FREQUENCY_RARE_POINTS


def test_internal_to_external_common_port_frequent_allow_is_low():
    flow = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", dst_port=443,
        protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
        occurrence_count=100, dominant_action="Allow", validation_status="pending",
    )

    result = qe.qualify(flow)

    # 5 (interne->externe) + 0 (port courant) + 0 (frequent) + 10 (Allow) = 15
    assert result["criticality_score"] == 15.0
    assert result["criticality_label"] == "low"
    assert result["security_status"] == "unknown"  # pending + low


def test_unclassified_zone_is_flagged_not_silently_ignored():
    # cas réel confirmé (docs/01-journal-technique.md, addendum étape 5) : certains flux
    # n'ont pas de zone du tout dans le log source.
    flow = Flow(
        source="SITE-B-FWTEST", src_ip="10.20.1.1", dst_ip="10.20.1.2", protocol="icmp",
        ingress_zone=None, egress_zone=None, occurrence_count=1, dominant_action="Block",
    )

    result = qe.qualify(flow)

    assert result["qualification_reasons"]["zone"]["category"] == "zone_non_classifiee"
    assert result["qualification_reasons"]["zone"]["points"] == qe.ZONE_UNCLASSIFIED_POINTS


def test_validated_by_human_overrides_security_status():
    approved = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", dst_port=445,
        ingress_zone="Internet_Zone", egress_zone="Users_Zone", occurrence_count=1,
        dominant_action="Allow", validation_status="approved",
    )
    blocked = Flow(
        source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", dst_port=443,
        ingress_zone="Users_Zone", egress_zone="Internet_Zone", occurrence_count=100,
        dominant_action="Allow", validation_status="blocked",
    )

    assert qe.qualify(approved)["security_status"] == "legitimate"
    assert qe.qualify(blocked)["security_status"] == "at_risk"


def test_qualify_all_writes_results_and_returns_label_counts(session):
    session.add_all(
        [
            Flow(
                source="SITE-A-FWTEST", src_ip="203.0.113.1", dst_ip="10.10.1.1", dst_port=445,
                protocol="tcp", ingress_zone="Internet_Zone", egress_zone="Users_Zone",
                occurrence_count=1, dominant_action="Allow",
            ),
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", dst_port=443,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                occurrence_count=100, dominant_action="Allow",
            ),
        ]
    )
    session.commit()

    summary = qe.qualify_all(session)

    assert summary["total_qualified"] == 2
    assert summary["label_counts"] == {"critical": 1, "low": 1}

    flows = session.query(Flow).order_by(Flow.id).all()
    assert flows[0].criticality_label == "critical"
    assert flows[0].qualification_reasons is not None

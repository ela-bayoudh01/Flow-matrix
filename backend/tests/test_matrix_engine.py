import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Flow
from app.Services import matrix_engine


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed(session):
    flows = [
        Flow(
            source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.10", dst_port=443,
            protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
            occurrence_count=2, allow_count=2, block_count=0, dominant_action="Allow",
            total_initiator_bytes=100, total_responder_bytes=200, criticality_label="low",
        ),
        Flow(
            source="SITE-A-FWTEST", src_ip="10.10.1.2", dst_ip="203.0.113.20", dst_port=445,
            protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
            occurrence_count=1, allow_count=0, block_count=1, dominant_action="Block",
            total_initiator_bytes=10, total_responder_bytes=0, criticality_label="high",
        ),
        Flow(
            source="SITE-B-FWTEST", src_ip="10.20.1.1", dst_ip="10.20.2.1", dst_port=139,
            protocol="tcp", ingress_zone="DMZ_Zone", egress_zone="OPS_Zone",
            occurrence_count=5, allow_count=5, block_count=0, dominant_action="Allow",
            total_initiator_bytes=50, total_responder_bytes=50, criticality_label=None,
        ),
    ]
    session.add_all(flows)
    session.commit()
    return flows


def test_zone_dimension_groups_flows_by_ingress_egress_zone(session):
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="zone")
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert ("Users_Zone", "Internet_Zone") in by_key
    users_to_internet = by_key[("Users_Zone", "Internet_Zone")]
    assert users_to_internet["flow_count"] == 2
    assert users_to_internet["allow_count"] == 2
    assert users_to_internet["block_count"] == 1
    assert users_to_internet["total_bytes"] == 100 + 200 + 10 + 0
    assert users_to_internet["criticality_breakdown"] == {"low": 1, "high": 1}

    assert ("DMZ_Zone", "OPS_Zone") in by_key
    assert by_key[("DMZ_Zone", "OPS_Zone")]["criticality_breakdown"] == {"non_qualifie": 1}


def test_ip_dimension_uses_a_different_grouping_without_changing_the_engine_logic(session):
    # Preuve que la dimension n'est pas figée : "ip" fonctionne avec le même moteur.
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="ip")
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert ("10.10.1.1", "203.0.113.10") in by_key
    assert by_key[("10.10.1.1", "203.0.113.10")]["flow_count"] == 1
    assert ("10.10.1.2", "203.0.113.20") in by_key


def test_source_filter_restricts_the_matrix_to_one_site(session):
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="zone", source="SITE-B-FWTEST")

    assert len(cells) == 1
    assert cells[0]["row"] == "DMZ_Zone"
    assert cells[0]["col"] == "OPS_Zone"


def test_unknown_dimension_raises_explicit_error(session):
    with pytest.raises(ValueError):
        matrix_engine.build_matrix(session, dimension="not_a_real_dimension")


def test_action_filter_recomputes_aggregates_not_just_hides_cells(session):
    # Le filtre doit changer les CHIFFRES de la cellule (recalculée sur le sous-ensemble
    # filtré), pas juste masquer des lignes après coup -- sinon les totaux seraient faux.
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="zone", dominant_action="Block")
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert ("Users_Zone", "Internet_Zone") in by_key
    cell = by_key[("Users_Zone", "Internet_Zone")]
    assert cell["flow_count"] == 1  # seul le Flow Block compte, pas les 2 de la cellule complète
    assert cell["allow_count"] == 0
    assert cell["block_count"] == 1
    assert ("DMZ_Zone", "OPS_Zone") not in by_key  # aucun Flow Block dans cette cellule


def test_ingress_zone_filter_restricts_matrix_to_that_row(session):
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="zone", ingress_zone="DMZ_Zone")

    assert len(cells) == 1
    assert cells[0]["row"] == "DMZ_Zone"


def test_matrix_rejects_unknown_filter(session):
    with pytest.raises(ValueError):
        matrix_engine.build_matrix(session, dimension="zone", not_a_real_filter="x")


def test_flows_with_no_zone_get_an_explicit_label_not_hidden(session):
    # Cas réel confirmé : certains événements ICMP dérivés n'ont pas de zone dans le log
    # source (docs/01-journal-technique.md, addendum étape 5). La cellule doit rester
    # visible et comptée, jamais masquée.
    session.add(
        Flow(
            source="SITE-B-FWTEST", src_ip="10.20.253.61", dst_ip="10.21.32.23", protocol="icmp",
            ingress_zone=None, egress_zone=None, occurrence_count=2, block_count=2,
            dominant_action="Block",
        )
    )
    session.commit()

    cells = matrix_engine.build_matrix(session, dimension="zone")

    assert len(cells) == 1
    assert cells[0]["row"] == matrix_engine.UNSET_LABEL
    assert cells[0]["col"] == matrix_engine.UNSET_LABEL
    assert cells[0]["flow_count"] == 1

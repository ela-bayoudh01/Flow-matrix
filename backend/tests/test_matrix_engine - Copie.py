from datetime import datetime, timedelta

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
            total_initiator_bytes=100, total_responder_bytes=200, total_connection_duration=10,
            criticality_label="low",
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

    cells = matrix_engine.build_matrix(session, dimension="zone")["cells"]
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert ("Users_Zone", "Internet_Zone") in by_key
    users_to_internet = by_key[("Users_Zone", "Internet_Zone")]
    assert users_to_internet["flow_count"] == 2
    assert users_to_internet["allow_count"] == 2
    assert users_to_internet["block_count"] == 1
    assert users_to_internet["total_bytes"] == 100 + 200 + 10 + 0
    assert users_to_internet["total_duration_seconds"] == 10  # seul le 1er Flow en a une
    assert users_to_internet["criticality_breakdown"] == {"low": 1, "high": 1}

    assert ("DMZ_Zone", "OPS_Zone") in by_key
    assert by_key[("DMZ_Zone", "OPS_Zone")]["criticality_breakdown"] == {"non_qualifie": 1}


def test_ip_dimension_uses_a_different_grouping_without_changing_the_engine_logic(session):
    # Preuve que la dimension n'est pas figée : "ip" fonctionne avec le même moteur.
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="ip")["cells"]
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert ("10.10.1.1", "203.0.113.10") in by_key
    assert by_key[("10.10.1.1", "203.0.113.10")]["flow_count"] == 1
    assert ("10.10.1.2", "203.0.113.20") in by_key


def test_source_filter_restricts_the_matrix_to_one_site(session):
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="zone", source="SITE-B-FWTEST")["cells"]

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

    cells = matrix_engine.build_matrix(session, dimension="zone", dominant_action="Block")["cells"]
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert ("Users_Zone", "Internet_Zone") in by_key
    cell = by_key[("Users_Zone", "Internet_Zone")]
    assert cell["flow_count"] == 1  # seul le Flow Block compte, pas les 2 de la cellule complète
    assert cell["allow_count"] == 0
    assert cell["block_count"] == 1
    assert ("DMZ_Zone", "OPS_Zone") not in by_key  # aucun Flow Block dans cette cellule


def test_ingress_zone_filter_restricts_matrix_to_that_row(session):
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="zone", ingress_zone="DMZ_Zone")["cells"]

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

    cells = matrix_engine.build_matrix(session, dimension="zone")["cells"]

    assert len(cells) == 1
    assert cells[0]["row"] == matrix_engine.UNSET_LABEL
    assert cells[0]["col"] == matrix_engine.UNSET_LABEL
    assert cells[0]["flow_count"] == 1


# --- Nouvelles dimensions (extension 2026-08-13, encadrant validé) -----------------------


def test_source_zone_dimension_groups_by_source_and_egress_zone(session):
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="source_zone")["cells"]
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert ("SITE-A-FWTEST", "Internet_Zone") in by_key
    assert by_key[("SITE-A-FWTEST", "Internet_Zone")]["flow_count"] == 2
    assert ("SITE-B-FWTEST", "OPS_Zone") in by_key


def test_zone_port_dimension_groups_by_ingress_zone_and_dst_port(session):
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="zone_port")["cells"]
    by_key = {(c["row"], c["col"]): c for c in cells}

    # col est toujours une chaîne en sortie (MatrixCell.col: str), même quand la donnée
    # source (dst_port) est un entier -- cf. bug trouvé en vérifiant sur flow_matrix.db réel.
    assert ("Users_Zone", "443") in by_key
    assert ("Users_Zone", "445") in by_key


def test_zone_action_dimension_groups_by_ingress_zone_and_dominant_action(session):
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="zone_action")["cells"]
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert by_key[("Users_Zone", "Allow")]["flow_count"] == 1
    assert by_key[("Users_Zone", "Block")]["flow_count"] == 1


def test_direction_criticality_dimension_reuses_qualification_engine_zone_roles(session):
    # Users_Zone (interne) -> Internet_Zone (externe) : même classification que
    # Qualification Engine._score_zone (docs/07), pas une nouvelle logique inventée ici.
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="direction_criticality")["cells"]
    rows = {c["row"] for c in cells}

    assert "interne_vers_externe" in rows
    # DMZ_Zone/OPS_Zone ne sont pas dans ZONE_ROLES -- classification honnête "inconnue",
    # jamais un rôle deviné par défaut.
    assert "inconnue_vers_inconnue" in rows


def test_port_category_zone_dimension_reuses_qualification_engine_sensitive_ports(session):
    # dst_port 445 (SMB) est dans SENSITIVE_PORTS, 443 dans COMMON_SAFE_PORTS -- même
    # classification que Qualification Engine._score_port (docs/07).
    _seed(session)

    cells = matrix_engine.build_matrix(session, dimension="port_category_zone")["cells"]
    by_key = {(c["row"], c["col"]): c for c in cells}

    assert ("port_courant", "Users_Zone") in by_key  # port 443
    assert ("port_sensible", "Users_Zone") in by_key  # port 445
    assert ("port_sensible", "DMZ_Zone") in by_key  # port 139 (SMB)


def test_timeslot_zone_dimension_is_gated_below_the_minimum_observation_window(session):
    base = datetime(2026, 1, 1, 10, 0, 0)
    session.add(
        Flow(
            source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.10", protocol="tcp",
            ingress_zone="Users_Zone", egress_zone="Internet_Zone",
            first_seen_at=base, last_seen_at=base + timedelta(hours=2),
        )
    )
    session.commit()

    result = matrix_engine.build_matrix(session, dimension="timeslot_zone")

    assert result["notice"] is not None
    assert "seuil de fiabilité" in result["notice"]
    assert len(result["cells"]) == 1  # jamais caché, juste annoté


def test_timeslot_zone_dimension_notice_is_none_once_window_is_long_enough(session):
    base = datetime(2026, 1, 1, 10, 0, 0)
    session.add_all(
        [
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.10", protocol="tcp",
                ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                first_seen_at=base, last_seen_at=base,
            ),
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.2", dst_ip="203.0.113.20", protocol="tcp",
                ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                first_seen_at=base, last_seen_at=base + timedelta(days=20),
            ),
        ]
    )
    session.commit()

    result = matrix_engine.build_matrix(session, dimension="timeslot_zone")

    assert result["notice"] is None


def test_dimension_notice_is_none_for_non_gated_dimensions(session):
    _seed(session)

    result = matrix_engine.build_matrix(session, dimension="zone")

    assert result["notice"] is None


def test_dimension_notice_warns_on_a_large_cell_count(session):
    # Mesuré sur flow_matrix.db réel : "ip" produit 31 050 cellules -- pas un problème de
    # lenteur en soi (~1s), mais un volume peu exploitable sans filtre. Seuil générique
    # (LARGE_RESULT_CELL_THRESHOLD), pas spécifique à "ip".
    session.add_all(
        [
            Flow(source="SITE-A-FWTEST", src_ip=f"10.10.1.{i}", dst_ip=f"203.0.113.{i}", protocol="tcp")
            for i in range(1, 1002)
        ]
    )
    session.commit()

    result = matrix_engine.build_matrix(session, dimension="ip")

    assert len(result["cells"]) > matrix_engine.LARGE_RESULT_CELL_THRESHOLD
    assert result["notice"] is not None
    assert "volume élevé" in result["notice"]

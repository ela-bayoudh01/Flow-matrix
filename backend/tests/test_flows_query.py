import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from datetime import datetime

from app.database import Base
from app.flows_query import list_flows, list_known_sources, list_source_coverage
from app.models import Flow, LogEntry


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed(session):
    # cycle_occurrence_count=1 sur les 3 -- nécessaire depuis le 2026-09-12 (correction d'un
    # bug réel) : le drill-down d'une cellule (dimension/row_value/col_value) exclut désormais
    # les Flow inactifs depuis la dernière clôture de cycle (Flow.cycle_occurrence_count == 0),
    # même filtre que Services/matrix_engine.py::build_matrix -- sans ce miroir, les tests de
    # drill-down ci-dessous perdraient les 3 Flow. Sans incidence sur les tests sans
    # dimension (Table des flux), qui n'appliquent jamais ce filtre.
    session.add_all(
        [
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.10", dst_port=443,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                dominant_action="Allow", criticality_label="low", cycle_occurrence_count=1,
            ),
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.2", dst_ip="203.0.113.20", dst_port=445,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                dominant_action="Block", criticality_label="high", cycle_occurrence_count=1,
            ),
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.3", dst_ip="203.0.113.30", dst_port=443,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                dominant_action="Mixed", criticality_label=None, cycle_occurrence_count=1,
            ),
        ]
    )
    session.commit()


def test_filters_restrict_items_and_summary_together(session):
    _seed(session)

    result = list_flows(session, ingress_zone="Users_Zone", egress_zone="Internet_Zone", dst_port=443)

    assert result["total_count"] == 2
    assert {f.dst_ip for f in result["items"]} == {"203.0.113.10", "203.0.113.30"}
    assert result["summary"]["total_flows"] == 2
    assert result["summary"]["allow_count"] == 2  # Allow (1) + Mixed (1)
    assert result["summary"]["block_count"] == 1  # Mixed (1)


def test_summary_criticality_breakdown_labels_unqualified_flows(session):
    _seed(session)

    result = list_flows(session, ingress_zone="Users_Zone", egress_zone="Internet_Zone")

    assert result["summary"]["criticality_breakdown"] == {"low": 1, "high": 1, "non_qualifie": 1}


def test_pagination_limit_and_offset(session):
    _seed(session)

    page = list_flows(session, limit=1, offset=1)

    assert page["total_count"] == 3  # total non affecté par la pagination
    assert len(page["items"]) == 1


def test_unknown_filter_raises_explicit_error(session):
    with pytest.raises(ValueError):
        list_flows(session, not_a_real_filter="x")


# --- Drill-down générique (dimension/row_value/col_value), extension 2026-08-13 ------------


def test_cell_drill_down_works_for_the_zone_dimension_like_before(session):
    _seed(session)

    result = list_flows(session, dimension="zone", row_value="Users_Zone", col_value="Internet_Zone")

    assert result["total_count"] == 3


def test_cell_drill_down_works_for_a_non_zone_dimension(session):
    # C'est exactement le bug qu'aurait laissé passer un drill-down encore câblé en dur sur
    # ingress_zone/egress_zone : "zone_port" n'a rien à voir avec egress_zone.
    _seed(session)

    result = list_flows(session, dimension="zone_port", row_value="Users_Zone", col_value="443")

    assert result["total_count"] == 2
    assert {f.dst_ip for f in result["items"]} == {"203.0.113.10", "203.0.113.30"}


def test_cell_drill_down_works_for_a_derived_dimension(session):
    # "direction" n'est pas une colonne Flow -- même expression que matrix_engine, jamais
    # une deuxième logique susceptible de diverger.
    _seed(session)

    result = list_flows(session, dimension="direction_criticality", row_value="interne_vers_externe", col_value="high")

    assert result["total_count"] == 1
    assert result["items"][0].dst_ip == "203.0.113.20"


def test_cell_drill_down_can_combine_with_a_regular_filter(session):
    _seed(session)

    result = list_flows(session, dimension="zone", row_value="Users_Zone", col_value="Internet_Zone", dominant_action="Block")

    assert result["total_count"] == 1


def test_cell_drill_down_requires_row_and_col_value_together(session):
    with pytest.raises(ValueError):
        list_flows(session, dimension="zone", row_value="Users_Zone")


def test_cell_drill_down_excludes_flows_inactive_since_the_last_cycle_closure(session):
    # 2026-09-12, bug réel corrigé, signalé en testant le correctif du Matrix Engine : la
    # cellule affichait déjà le bon compte scopé au cycle courant (build_matrix()), mais
    # cliquer dessus ouvrait un tiroir listant TOUT l'historique de la combinaison -- le
    # drill-down doit rester rigoureusement cohérent avec le chiffre affiché sur la cellule.
    _seed(session)
    session.add(
        Flow(
            source="SITE-A-FWTEST", src_ip="10.10.1.4", dst_ip="203.0.113.40", dst_port=443,
            protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
            dominant_action="Allow", criticality_label="low", cycle_occurrence_count=0,  # inactif ce cycle
        )
    )
    session.commit()

    result = list_flows(session, dimension="zone", row_value="Users_Zone", col_value="Internet_Zone")

    assert result["total_count"] == 3  # les 3 de _seed(), pas le 4ᵉ inactif
    assert "203.0.113.40" not in {f.dst_ip for f in result["items"]}
    assert result["summary"]["total_flows"] == 3  # les tuiles du tiroir aussi, même filtre partagé


# --- Recherche par mot-clé (demande de l'encadrant, 2026-08-25) ----------------------------


def test_keyword_search_matches_across_several_columns(session):
    _seed(session)

    by_ip = list_flows(session, q="203.0.113.20")
    assert {f.dst_ip for f in by_ip["items"]} == {"203.0.113.20"}

    by_zone = list_flows(session, q="Internet_Zone")
    assert by_zone["total_count"] == 3  # les 3 flux seedés partagent cette zone

    by_port = list_flows(session, q="445")
    assert {f.dst_ip for f in by_port["items"]} == {"203.0.113.20"}  # port -> texte, pas seulement des colonnes texte


def test_keyword_search_is_case_insensitive_and_substring(session):
    _seed(session)

    result = list_flows(session, q="users_zone")  # casse différente de "Users_Zone" en base

    assert result["total_count"] == 3


def test_keyword_search_combines_with_other_filters(session):
    _seed(session)

    result = list_flows(session, q="203.0.113", dominant_action="Block")

    assert result["total_count"] == 1
    assert result["items"][0].dst_ip == "203.0.113.20"


def test_keyword_search_empty_string_matches_everything(session):
    _seed(session)

    result = list_flows(session, q="")

    assert result["total_count"] == 3


def test_keyword_search_no_match_returns_empty(session):
    _seed(session)

    result = list_flows(session, q="nope-nothing-matches-this")

    assert result["total_count"] == 0
    assert result["items"] == []


def test_keyword_search_also_restricts_the_summary(session):
    _seed(session)

    result = list_flows(session, q="203.0.113.20")

    assert result["summary"]["total_flows"] == 1
    assert result["summary"]["criticality_breakdown"] == {"high": 1}


# --- list_known_sources (2026-09-12, bug réel corrigé) -------------------------------------


def test_list_known_sources_returns_every_source_sorted(session):
    session.add_all(
        [
            Flow(source="SITE-B-FWTEST", src_ip="10.20.1.1", dst_ip="203.0.113.1", protocol="tcp"),
            Flow(source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.2", protocol="tcp"),
        ]
    )
    session.commit()

    assert list_known_sources(session) == ["SITE-A-FWTEST", "SITE-B-FWTEST"]


def test_list_known_sources_never_depends_on_cycle_occurrence_count(session):
    # Bug réel signalé juste après une clôture de cycle : cycle_occurrence_count == 0 pour
    # TOUS les Flow d'une source tant qu'aucun nouvel import n'a eu lieu depuis -- la source
    # doit rester listée (contrairement à Services/matrix_engine.py::build_matrix, qui lui
    # exclut délibérément ces Flow, un besoin différent).
    session.add(
        Flow(
            source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", protocol="tcp",
            cycle_occurrence_count=0, cycle_dominant_action=None,
        )
    )
    session.commit()

    assert list_known_sources(session) == ["SITE-A-FWTEST"]


def test_list_known_sources_deduplicates(session):
    session.add_all(
        [
            Flow(source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", protocol="tcp"),
            Flow(source="SITE-A-FWTEST", src_ip="10.10.1.2", dst_ip="203.0.113.2", protocol="tcp"),
        ]
    )
    session.commit()

    assert list_known_sources(session) == ["SITE-A-FWTEST"]


def test_list_known_sources_empty_returns_empty_list(session):
    assert list_known_sources(session) == []


# --- list_source_coverage (2026-09-12, demande de l'encadrant après démo) ------------------


def test_list_source_coverage_computes_period_and_flow_count_per_source(session):
    session.add_all(
        [
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", protocol="tcp",
                first_seen_at=datetime(2026, 9, 1, 8, 0), last_seen_at=datetime(2026, 9, 10, 14, 0),
            ),
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.2", dst_ip="203.0.113.2", protocol="tcp",
                first_seen_at=datetime(2026, 9, 5, 9, 0), last_seen_at=datetime(2026, 9, 12, 10, 0),
            ),
            Flow(
                source="SITE-B-FWTEST", src_ip="10.20.1.1", dst_ip="203.0.113.3", protocol="tcp",
                first_seen_at=datetime(2026, 9, 3, 0, 0), last_seen_at=datetime(2026, 9, 3, 1, 0),
            ),
        ]
    )
    session.commit()

    result = list_source_coverage(session)

    by_source = {item["source"]: item for item in result}
    assert by_source["SITE-A-FWTEST"]["first_seen_at"] == datetime(2026, 9, 1, 8, 0)  # le plus ancien des 2
    assert by_source["SITE-A-FWTEST"]["last_seen_at"] == datetime(2026, 9, 12, 10, 0)  # le plus récent des 2
    assert by_source["SITE-A-FWTEST"]["flow_count"] == 2
    assert by_source["SITE-B-FWTEST"]["flow_count"] == 1


def test_list_source_coverage_last_imported_at_comes_from_log_entries_not_flows(session):
    session.add(
        Flow(
            source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", protocol="tcp",
            first_seen_at=datetime(2026, 9, 1), last_seen_at=datetime(2026, 9, 1),
        )
    )
    session.add_all(
        [
            LogEntry(source="SITE-A-FWTEST", raw_line="x", ingested_at=datetime(2026, 9, 1, 12, 0)),
            LogEntry(source="SITE-A-FWTEST", raw_line="x", ingested_at=datetime(2026, 9, 11, 18, 30)),  # le plus récent
        ]
    )
    session.commit()

    result = list_source_coverage(session)

    assert result[0]["last_imported_at"] == datetime(2026, 9, 11, 18, 30)


def test_list_source_coverage_last_imported_at_none_when_no_log_entries(session):
    session.add(
        Flow(
            source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.1", protocol="tcp",
            first_seen_at=datetime(2026, 9, 1), last_seen_at=datetime(2026, 9, 1),
        )
    )
    session.commit()

    result = list_source_coverage(session)

    assert result[0]["last_imported_at"] is None


def test_list_source_coverage_empty_returns_empty_list(session):
    assert list_source_coverage(session) == []

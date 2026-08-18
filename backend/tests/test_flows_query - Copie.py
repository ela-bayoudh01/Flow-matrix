import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.flows_query import list_flows
from app.models import Flow


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed(session):
    session.add_all(
        [
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.1", dst_ip="203.0.113.10", dst_port=443,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                dominant_action="Allow", criticality_label="low",
            ),
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.2", dst_ip="203.0.113.20", dst_port=445,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                dominant_action="Block", criticality_label="high",
            ),
            Flow(
                source="SITE-A-FWTEST", src_ip="10.10.1.3", dst_ip="203.0.113.30", dst_port=443,
                protocol="tcp", ingress_zone="Users_Zone", egress_zone="Internet_Zone",
                dominant_action="Mixed", criticality_label=None,
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

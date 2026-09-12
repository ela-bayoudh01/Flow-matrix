import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Flow
from app.Services import subnet_observation as so

SOURCE_A = "SITE-A-FWTEST"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _flow(**overrides):
    defaults = dict(source=SOURCE_A, src_ip="10.10.1.1", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    defaults.update(overrides)
    return Flow(**defaults)


def test_observed_subnets_groups_by_prefix_default_24(session):
    session.add_all(
        [
            _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1"),
            _flow(src_ip="10.10.1.1", dst_ip="203.0.113.2"),  # même IP, un 2e Flow
            _flow(src_ip="10.10.1.2", dst_ip="203.0.113.1"),
            _flow(src_ip="10.10.2.1", dst_ip="203.0.113.1"),  # /24 différent
        ]
    )
    session.commit()

    result = so.observed_subnets(session, source=SOURCE_A)

    by_cidr = {r["cidr"]: r for r in result}
    assert by_cidr["10.10.1.0/24"]["machine_count"] == 2  # 10.10.1.1 et 10.10.1.2
    assert by_cidr["10.10.1.0/24"]["flow_count"] == 3  # 3 Flow au total dans ce préfixe
    assert by_cidr["10.10.2.0/24"]["machine_count"] == 1
    assert by_cidr["10.10.2.0/24"]["flow_count"] == 1


def test_observed_subnets_respects_a_finer_granularity(session):
    session.add_all(
        [
            _flow(src_ip="10.10.1.1", dst_ip="203.0.113.1"),
            _flow(src_ip="10.10.1.130", dst_ip="203.0.113.1"),  # /25 différent, même /24
        ]
    )
    session.commit()

    result_24 = so.observed_subnets(session, source=SOURCE_A, prefix_length=24)
    result_25 = so.observed_subnets(session, source=SOURCE_A, prefix_length=25)

    assert len(result_24) == 1  # les deux IP tombent dans le même /24
    assert len(result_25) == 2  # mais dans deux /25 distincts
    cidrs_25 = {r["cidr"] for r in result_25}
    assert cidrs_25 == {"10.10.1.0/25", "10.10.1.128/25"}


def test_observed_subnets_never_mixes_two_sources(session):
    session.add_all(
        [
            _flow(source=SOURCE_A, src_ip="10.10.1.1"),
            _flow(source="SITE-B-FWTEST", src_ip="10.10.1.2"),
        ]
    )
    session.commit()

    result = so.observed_subnets(session, source=SOURCE_A)

    assert len(result) == 1
    assert result[0]["machine_count"] == 1


def test_observed_subnets_skips_invalid_and_ipv6_addresses_without_crashing(session):
    session.add_all(
        [
            _flow(src_ip="10.10.1.1"),
            _flow(src_ip="not-an-ip", dst_ip="203.0.113.2"),
            _flow(src_ip="2001:db8::1", dst_ip="203.0.113.3"),
        ]
    )
    session.commit()

    result = so.observed_subnets(session, source=SOURCE_A)

    assert len(result) == 1  # seule l'IPv4 valide compte
    assert result[0]["cidr"] == "10.10.1.0/24"


def test_observed_subnets_rejects_out_of_range_prefix_length(session):
    with pytest.raises(ValueError):
        so.observed_subnets(session, source=SOURCE_A, prefix_length=0)
    with pytest.raises(ValueError):
        so.observed_subnets(session, source=SOURCE_A, prefix_length=33)


def test_observed_subnets_empty_source_returns_empty_list(session):
    assert so.observed_subnets(session, source="NOPE-FWTEST") == []


# --- cidr_for_ip (2026-09-11) -- helper extrait, réutilisé aussi par
# Services/validation_cycle_engine.py::compute_subnet_diff ---------------------------------


def test_cidr_for_ip_returns_the_network_at_the_given_prefix():
    assert so.cidr_for_ip("10.67.1.32", 24) == "10.67.1.0/24"
    assert so.cidr_for_ip("10.67.1.32", 27) == "10.67.1.32/27"


def test_cidr_for_ip_returns_none_for_an_invalid_address():
    assert so.cidr_for_ip("not-an-ip", 24) is None
    assert so.cidr_for_ip("", 24) is None


def test_cidr_for_ip_returns_none_for_ipv6():
    assert so.cidr_for_ip("2001:db8::1", 24) is None

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app import network_policies as np


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create(session, **overrides):
    defaults = dict(
        source="SITE-A-FWTEST", src_cidr="10.10.1.0/24", destination="Internet_Zone",
        protocol="tcp", dst_port=443, action="Block", justification="Test.", decided_by="Loulou",
    )
    defaults.update(overrides)
    return np.create_network_policy(session, **defaults)


def test_create_network_policy_persists_all_fields(session):
    policy = _create(session)

    assert policy.id is not None
    assert policy.source == "SITE-A-FWTEST"
    assert policy.src_cidr == "10.10.1.0/24"
    assert policy.destination == "Internet_Zone"
    assert policy.protocol == "tcp"
    assert policy.dst_port == 443
    assert policy.action == "Block"
    assert policy.justification == "Test."
    assert policy.decided_by == "Loulou"
    assert policy.created_at is not None


def test_create_network_policy_accepts_a_freeform_cidr_never_validated(session):
    # Demande explicite : le CIDR source est du texte libre, jamais contraint à une vraie
    # syntaxe CIDR -- accepte n'importe quoi, l'encadrant reste seul juge.
    policy = _create(session, src_cidr="pas vraiment un cidr mais accepte quand meme")

    assert policy.src_cidr == "pas vraiment un cidr mais accepte quand meme"


def test_list_network_policies_orders_most_recent_first(session):
    first = _create(session, destination="A")
    second = _create(session, destination="B")

    result = np.list_network_policies(session)

    assert [p.id for p in result["items"]] == [second.id, first.id]
    assert result["total_count"] == 2


def test_list_network_policies_filters_by_source(session):
    _create(session, source="SITE-A-FWTEST")
    _create(session, source="SITE-B-FWTEST")

    result = np.list_network_policies(session, source="SITE-A-FWTEST")

    assert result["total_count"] == 1
    assert result["items"][0].source == "SITE-A-FWTEST"


def test_list_network_policies_paginates(session):
    for i in range(5):
        _create(session, destination=f"dest-{i}")

    result = np.list_network_policies(session, limit=2, offset=1)

    assert result["total_count"] == 5
    assert len(result["items"]) == 2

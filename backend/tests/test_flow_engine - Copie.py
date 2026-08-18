import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import LogEntry
from app.parser import parse_line
from app.Services import flow_engine

from .sample_logs import ALLOW_HTTPS_LINE, ALLOW_HTTPS_LINE_REPEAT, BLOCK_SMB_LINE


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _log_entry_from(raw_line: str, source: str) -> LogEntry:
    return LogEntry(source=source, **parse_line(raw_line))


def test_two_observations_of_same_communication_consolidate_into_one_flow(session):
    entry_1 = _log_entry_from(ALLOW_HTTPS_LINE, source="SITE-A-FWTEST")
    entry_2 = _log_entry_from(ALLOW_HTTPS_LINE_REPEAT, source="SITE-A-FWTEST")
    session.add_all([entry_1, entry_2])
    session.flush()

    flow_1 = flow_engine.consolidate(session, entry_1)
    flow_2 = flow_engine.consolidate(session, entry_2)
    session.commit()

    assert flow_1.id == flow_2.id
    assert flow_1.occurrence_count == 2
    assert flow_1.allow_count == 2
    assert flow_1.block_count == 0
    assert flow_1.dominant_action == "Allow"
    assert flow_1.total_initiator_bytes == 1423 + 500
    assert flow_1.total_responder_bytes == 9856 + 4000


def test_mixed_allow_and_block_on_same_pair_yields_mixed_dominant_action(session):
    # même paire (src, dst, port, proto) que BLOCK_SMB_LINE mais action Allow (et ConnectionID
    # différent -- sinon on viole l'unicité (source, device_uuid, connection_id)), pour tester "Mixed"
    allow_variant = BLOCK_SMB_LINE.replace(
        "AccessControlRuleAction: Block", "AccessControlRuleAction: Allow"
    ).replace("ConnectionID: 50468", "ConnectionID: 50469")

    entry_block = _log_entry_from(BLOCK_SMB_LINE, source="SITE-A-FWTEST")
    entry_allow = _log_entry_from(allow_variant, source="SITE-A-FWTEST")
    session.add_all([entry_block, entry_allow])
    session.flush()

    flow_engine.consolidate(session, entry_block)
    flow = flow_engine.consolidate(session, entry_allow)
    session.commit()

    assert flow.allow_count == 1
    assert flow.block_count == 1
    assert flow.dominant_action == "Mixed"


def test_flow_cache_avoids_a_db_query_on_repeated_observations(session, monkeypatch):
    entry_1 = _log_entry_from(ALLOW_HTTPS_LINE, source="SITE-A-FWTEST")
    entry_2 = _log_entry_from(ALLOW_HTTPS_LINE_REPEAT, source="SITE-A-FWTEST")
    session.add_all([entry_1, entry_2])
    session.flush()

    cache: flow_engine.FlowCache = {}
    flow_1 = flow_engine.consolidate(session, entry_1, cache)

    from sqlalchemy.orm import Query

    query_count = 0
    original_first = Query.first

    def counting_first(self, *args, **kwargs):
        nonlocal query_count
        query_count += 1
        return original_first(self, *args, **kwargs)

    monkeypatch.setattr(Query, "first", counting_first)
    flow_2 = flow_engine.consolidate(session, entry_2, cache)

    assert flow_2.id == flow_1.id
    assert query_count == 0  # servi par le cache, aucune requête base


def test_last_observed_fields_follow_chronological_order_not_insertion_order(session):
    # entry_2 (23:40) est chronologiquement après entry_1 (23:34) mais on la traite en premier :
    # last_access_control_rule_name/zones doivent quand même refléter la plus récente par date.
    entry_recent = _log_entry_from(ALLOW_HTTPS_LINE_REPEAT, source="SITE-A-FWTEST")
    entry_older = _log_entry_from(ALLOW_HTTPS_LINE, source="SITE-A-FWTEST")
    session.add_all([entry_recent, entry_older])
    session.flush()

    flow_engine.consolidate(session, entry_recent)
    flow = flow_engine.consolidate(session, entry_older)  # traité après, mais plus ancien
    session.commit()

    assert flow.last_seen_at == entry_recent.first_packet_at
    assert flow.first_seen_at == entry_older.first_packet_at

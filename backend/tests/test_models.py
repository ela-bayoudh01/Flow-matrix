import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AclProposal, Flow, LogEntry


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_log_entry_consolidates_into_flow(session):
    flow = Flow(
        source="SITE-A-FWTEST",
        src_ip="10.10.1.32",
        dst_ip="203.0.113.10",
        dst_port=443,
        protocol="tcp",
        occurrence_count=1,
        allow_count=1,
        dominant_action="Allow",
    )
    session.add(flow)
    session.flush()

    log_entry = LogEntry(
        source="SITE-A-FWTEST",
        raw_line="Jun 28 23:34:06 10.10.64.254  : %FTD-6-430003: ...",
        firewall_device_ip="10.10.64.254",
        device_uuid="00000000-0000-4000-a000-000000000001",
        connection_id=50437,
        access_control_rule_action="Allow",
        src_ip="10.10.1.32",
        dst_ip="203.0.113.10",
        dst_port=443,
        protocol="tcp",
        flow=flow,
        extra={"URLCategory": "Computer Security", "SSLVersion": "Unknown"},
    )
    session.add(log_entry)
    session.commit()

    assert flow.log_entries == [log_entry]
    assert log_entry.flow.dst_ip == "203.0.113.10"
    assert log_entry.extra["URLCategory"] == "Computer Security"


def test_flow_identity_uniqueness_is_enforced(session):
    kwargs = dict(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    session.add(Flow(**kwargs))
    session.commit()

    session.add(Flow(**kwargs))
    with pytest.raises(IntegrityError):
        session.commit()


def test_acl_proposal_can_group_several_flows(session):
    flow_1 = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="10.12.1.100", dst_port=445, protocol="tcp")
    flow_2 = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.33", dst_ip="10.12.1.100", dst_port=445, protocol="tcp")
    proposal = AclProposal(
        source="SITE-A-FWTEST",
        proposed_action="Deny",
        proposed_rule_text="access-list ... deny tcp 10.10.1.0 0.0.0.255 host 10.12.1.100 eq 445",
        flows=[flow_1, flow_2],
    )
    session.add(proposal)
    session.commit()

    assert set(proposal.flows) == {flow_1, flow_2}
    assert flow_1.acl_proposals == [proposal]
    assert flow_2.acl_proposals == [proposal]


def test_deleting_flow_preserves_log_entries_but_removes_proposal_link(session):
    flow = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    log_entry = LogEntry(
        source="SITE-A-FWTEST",
        raw_line="raw",
        device_uuid="uuid",
        connection_id=1,
        src_ip="10.10.1.32",
        dst_ip="203.0.113.10",
        flow=flow,
    )
    session.add(log_entry)
    session.commit()

    session.delete(flow)
    session.commit()

    refreshed = session.get(LogEntry, log_entry.id)
    assert refreshed is not None
    assert refreshed.flow_id is None

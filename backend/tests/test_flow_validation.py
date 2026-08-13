import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.flow_validation import apply_validation
from app.models import Flow, FlowValidationHistory


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_apply_validation_updates_flow_and_records_history(session):
    flow = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    session.add(flow)
    session.commit()
    assert flow.validation_status == "pending"

    apply_validation(session, flow, "approved", "Loulou")

    assert flow.validation_status == "approved"
    assert flow.validated_by == "Loulou"
    assert flow.validated_at is not None

    history = session.query(FlowValidationHistory).filter_by(flow_id=flow.id).one()
    assert history.old_status == "pending"
    assert history.new_status == "approved"
    assert history.validated_by == "Loulou"


def test_two_successive_validations_produce_two_history_entries_in_order(session):
    flow = Flow(source="SITE-A-FWTEST", src_ip="10.10.1.32", dst_ip="203.0.113.10", dst_port=443, protocol="tcp")
    session.add(flow)
    session.commit()

    apply_validation(session, flow, "approved", "Loulou")
    apply_validation(session, flow, "blocked", "Encadrant")

    history = flow.validation_history
    assert len(history) == 2
    assert (history[0].old_status, history[0].new_status) == ("pending", "approved")
    assert (history[1].old_status, history[1].new_status) == ("approved", "blocked")
    assert history[1].validated_by == "Encadrant"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.acl_proposal_review import apply_acl_proposal_review
from app.database import Base
from app.models import AclProposal, AclProposalHistory


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_apply_review_updates_proposal_and_records_history(session):
    proposal = AclProposal(source="SITE-A-FWTEST", intent="manual", proposed_action="Allow")
    session.add(proposal)
    session.commit()
    assert proposal.status == "pending"

    apply_acl_proposal_review(session, proposal, "approved", "Loulou")

    assert proposal.status == "approved"
    assert proposal.validated_by == "Loulou"
    assert proposal.validated_at is not None

    history = session.query(AclProposalHistory).filter_by(acl_proposal_id=proposal.id).one()
    assert history.old_status == "pending"
    assert history.new_status == "approved"
    assert history.changed_by == "Loulou"


def test_two_successive_reviews_produce_two_history_entries_in_order(session):
    proposal = AclProposal(source="SITE-A-FWTEST", intent="manual", proposed_action="Allow")
    session.add(proposal)
    session.commit()

    apply_acl_proposal_review(session, proposal, "approved", "Loulou")
    apply_acl_proposal_review(session, proposal, "rejected", "Encadrant")

    history = proposal.history
    assert len(history) == 2
    assert (history[0].old_status, history[0].new_status) == ("pending", "approved")
    assert (history[1].old_status, history[1].new_status) == ("approved", "rejected")
    assert history[1].changed_by == "Encadrant"

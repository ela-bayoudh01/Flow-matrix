"""Consultation d'AclProposalHistory, avec le contexte de la proposition concernée inclus
directement -- même principe que validation_history_query.py pour les Flow.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import AclProposal, AclProposalHistory

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


def list_acl_proposal_history(
    session: Session,
    *,
    acl_proposal_id: Optional[int] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    query = session.query(AclProposalHistory).join(AclProposal, AclProposalHistory.acl_proposal_id == AclProposal.id)
    if acl_proposal_id is not None:
        query = query.filter(AclProposalHistory.acl_proposal_id == acl_proposal_id)

    total_count = query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = query.order_by(AclProposalHistory.created_at.desc()).offset(offset).limit(limit).all()

    return {"items": items, "total_count": total_count}

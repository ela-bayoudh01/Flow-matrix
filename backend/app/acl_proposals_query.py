"""Consultation des propositions de règles ACL (AclProposal)."""

from typing import Optional

from sqlalchemy.orm import Session

from .models import AclProposal

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


def list_acl_proposals(
    session: Session,
    *,
    status: Optional[str] = None,
    intent: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    query = session.query(AclProposal)
    if status is not None:
        query = query.filter(AclProposal.status == status)
    if intent is not None:
        query = query.filter(AclProposal.intent == intent)
    if source is not None:
        query = query.filter(AclProposal.source == source)

    total_count = query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = query.order_by(AclProposal.created_at.desc()).offset(offset).limit(limit).all()

    return {"items": items, "total_count": total_count}

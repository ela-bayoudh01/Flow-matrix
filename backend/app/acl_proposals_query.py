"""Consultation des propositions de règles ACL (AclProposal)."""

from typing import Optional

from sqlalchemy.orm import Session

from .models import AclProposal
from .search_utils import apply_keyword_search

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

# Colonnes cherchées par la barre de recherche par mot-clé (demande de l'encadrant, 2026-08-25).
SEARCH_COLUMNS = [
    AclProposal.source, AclProposal.intent, AclProposal.ingress_zone, AclProposal.egress_zone,
    AclProposal.target_rule_name, AclProposal.suggested_rule_name, AclProposal.proposed_action,
]


def list_acl_proposals(
    session: Session,
    *,
    status: Optional[str] = None,
    intent: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    query = apply_keyword_search(session.query(AclProposal), q, SEARCH_COLUMNS)
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

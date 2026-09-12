"""Consultation des findings du Recommendation Engine (RuleRecommendation)."""

from typing import Optional

from sqlalchemy.orm import Session

from .models import RuleRecommendation
from .search_utils import apply_keyword_search

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

# Colonnes cherchées par la barre de recherche par mot-clé (demande de l'encadrant, 2026-08-25).
SEARCH_COLUMNS = [
    RuleRecommendation.source, RuleRecommendation.finding_type, RuleRecommendation.rule_name,
    RuleRecommendation.ingress_zone, RuleRecommendation.egress_zone,
]


def list_recommendations(
    session: Session,
    *,
    status: Optional[str] = None,
    finding_type: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    query = apply_keyword_search(session.query(RuleRecommendation), q, SEARCH_COLUMNS)
    if status is not None:
        query = query.filter(RuleRecommendation.status == status)
    if finding_type is not None:
        query = query.filter(RuleRecommendation.finding_type == finding_type)
    if source is not None:
        query = query.filter(RuleRecommendation.source == source)

    total_count = query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = query.order_by(RuleRecommendation.created_at.desc()).offset(offset).limit(limit).all()

    return {"items": items, "total_count": total_count}

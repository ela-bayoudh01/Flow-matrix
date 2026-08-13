"""Requête filtrée sur les Flow. Utilisée à la fois par la vue "table plate" et par le
drill-down d'une cellule de matrice (même endpoint, filtres différents -- cf. docs/00 §3ter :
les deux vues doivent rester cohérentes puisqu'elles lisent la même source de vérité).
"""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .flow_filters import FILTER_COLUMNS, apply_filters
from .models import Flow

MAX_LIMIT = 1000
DEFAULT_LIMIT = 200


def list_flows(
    session: Session,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    **filters,
) -> dict:
    unknown = set(filters) - set(FILTER_COLUMNS)
    if unknown:
        raise ValueError(f"Filtre(s) inconnu(s) : {sorted(unknown)}")

    base_query = apply_filters(session.query(Flow), filters)

    total_count = base_query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = base_query.order_by(Flow.id).offset(offset).limit(limit).all()

    return {"items": items, "total_count": total_count, "summary": _summarize(session, filters)}


def _summarize(session: Session, filters: dict) -> dict:
    action_query = apply_filters(
        session.query(Flow.dominant_action, func.count(Flow.id)), filters
    ).group_by(Flow.dominant_action)
    action_counts: dict[Optional[str], int] = dict(action_query.all())
    # un Flow "Mixed" compte à la fois dans allow et block : c'est bien un flux qui a été
    # à la fois autorisé et bloqué au moins une fois, les deux infos sont pertinentes.
    allow_count = action_counts.get("Allow", 0) + action_counts.get("Mixed", 0)
    block_count = action_counts.get("Block", 0) + action_counts.get("Mixed", 0)

    criticality_query = apply_filters(
        session.query(Flow.criticality_label, func.count(Flow.id)), filters
    ).group_by(Flow.criticality_label)
    criticality_breakdown = {(label or "non_qualifie"): count for label, count in criticality_query.all()}

    return {
        "total_flows": sum(action_counts.values()),
        "allow_count": allow_count,
        "block_count": block_count,
        "criticality_breakdown": criticality_breakdown,
    }

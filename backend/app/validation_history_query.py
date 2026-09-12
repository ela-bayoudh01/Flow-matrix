"""Consultation de FlowValidationHistory, avec le contexte du Flow concerné (src/dst/port/
protocole) inclus directement -- évite un second appel API pour afficher la page Historique.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import Flow, FlowValidationHistory
from .search_utils import apply_keyword_search

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

# Colonnes cherchées par la barre de recherche par mot-clé (demande de l'encadrant,
# 2026-08-25) -- mélange History (old_status/new_status/validated_by) et Flow (contexte
# affiché : src/dst/port/protocole/source), jamais une deuxième liste par ailleurs.
SEARCH_COLUMNS = [
    Flow.source, Flow.src_ip, Flow.dst_ip, Flow.dst_port, Flow.protocol,
    FlowValidationHistory.old_status, FlowValidationHistory.new_status, FlowValidationHistory.validated_by,
]


def list_validation_history(
    session: Session,
    *,
    flow_id: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    query = apply_keyword_search(
        session.query(FlowValidationHistory, Flow).join(Flow, FlowValidationHistory.flow_id == Flow.id), q, SEARCH_COLUMNS
    )
    if flow_id is not None:
        query = query.filter(FlowValidationHistory.flow_id == flow_id)

    total_count = query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    rows = query.order_by(FlowValidationHistory.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        {
            "id": history.id,
            "flow_id": history.flow_id,
            "source": flow.source,
            "src_ip": flow.src_ip,
            "dst_ip": flow.dst_ip,
            "dst_port": flow.dst_port,
            "protocol": flow.protocol,
            "old_status": history.old_status,
            "new_status": history.new_status,
            "validated_by": history.validated_by,
            "created_at": history.created_at,
            "justification": history.justification,
            "observed_action_before": history.observed_action_before,
            "decided_action": history.decided_action,
        }
        for history, flow in rows
    ]
    return {"items": items, "total_count": total_count}

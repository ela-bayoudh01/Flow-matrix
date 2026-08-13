"""Consultation de FlowValidationHistory, avec le contexte du Flow concerné (src/dst/port/
protocole) inclus directement -- évite un second appel API pour afficher la page Historique.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import Flow, FlowValidationHistory

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


def list_validation_history(
    session: Session,
    *,
    flow_id: Optional[int] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    query = session.query(FlowValidationHistory, Flow).join(Flow, FlowValidationHistory.flow_id == Flow.id)
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
        }
        for history, flow in rows
    ]
    return {"items": items, "total_count": total_count}

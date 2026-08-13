"""Applique une décision de validation humaine sur un Flow et trace le changement dans
FlowValidationHistory (qui, quand, ancien -> nouveau statut). Les deux écritures sont
toujours faites ensemble : jamais de changement de validation_status sans trace.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import Flow, FlowValidationHistory
from .time_utils import utcnow


def apply_validation(session: Session, flow: Flow, status: str, validated_by: Optional[str]) -> Flow:
    old_status = flow.validation_status

    flow.validation_status = status
    flow.validated_by = validated_by
    flow.validated_at = utcnow()

    session.add(
        FlowValidationHistory(
            flow_id=flow.id,
            old_status=old_status,
            new_status=status,
            validated_by=validated_by,
        )
    )

    session.commit()
    session.refresh(flow)
    return flow

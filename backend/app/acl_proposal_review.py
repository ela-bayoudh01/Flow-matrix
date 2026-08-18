"""Applique une décision de revue humaine sur une AclProposal et trace le changement dans
AclProposalHistory (qui, quand, ancien -> nouveau statut). Les deux écritures sont toujours
faites ensemble : jamais de changement de statut sans trace -- même principe que
app/flow_validation.py pour les Flow.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import AclProposal, AclProposalHistory
from .time_utils import utcnow


def apply_acl_proposal_review(session: Session, proposal: AclProposal, status: str, validated_by: Optional[str]) -> AclProposal:
    old_status = proposal.status

    proposal.status = status
    proposal.validated_by = validated_by
    proposal.validated_at = utcnow()

    session.add(
        AclProposalHistory(
            acl_proposal_id=proposal.id,
            old_status=old_status,
            new_status=status,
            changed_by=validated_by,
        )
    )

    session.commit()
    session.refresh(proposal)
    return proposal

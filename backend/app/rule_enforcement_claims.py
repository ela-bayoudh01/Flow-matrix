"""Module "Déclarer la réclamation" sur un flux "Règle non appliquée" (2026-09-10, demande de
l'encadrant) -- constate explicitement qu'une décision (Flow.decided_action) n'est toujours
pas honorée par le pare-feu, distinct du "Changer la règle" qui PREND une décision (voir
flow_validation.py). `first_detected_at` est posé automatiquement ailleurs (Services/
validation_cycle_engine.py::_ensure_claims_detected, au moment du calcul du diff) -- ce
module ne touche jamais que `last_claimed_at`/`claim_count`, sur une action humaine explicite.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import Flow, FlowValidationHistory, RuleEnforcementClaim
from .time_utils import utcnow


def declare_claim(session: Session, flow: Flow) -> RuleEnforcementClaim:
    """Enregistre une réclamation -- crée la ligne de suivi si elle n'existe pas encore
    (normalement déjà créée par la détection passive du diff, mais jamais fait confiance à
    cet ordre : une réclamation doit rester possible même si ce cas de figure venait à
    manquer), sinon incrémente `claim_count` et met à jour `last_claimed_at`. `first_detected_at`
    n'est JAMAIS modifié ici une fois posé -- toujours la première fois vue, jamais réécrite.
    """
    claim = session.query(RuleEnforcementClaim).filter_by(flow_id=flow.id).one_or_none()
    now = utcnow()
    if claim is None:
        claim = RuleEnforcementClaim(flow_id=flow.id, first_detected_at=now, claim_count=1, last_claimed_at=now)
        session.add(claim)
    else:
        claim.claim_count += 1
        claim.last_claimed_at = now

    session.commit()
    session.refresh(claim)
    return claim


def get_current_decision_history(session: Session, flow: Flow) -> Optional[FlowValidationHistory]:
    """La ligne FlowValidationHistory qui a posé la decided_action ACTUELLE de ce Flow --
    toujours la plus récente entrée avec justification non nulle (chaque "Changer la règle"
    met à jour Flow.decided_action et crée cette entrée dans la même transaction, cf.
    flow_validation.py::apply_rule_change -- les deux restent donc toujours synchronisés).
    None si ce Flow n'a jamais eu de "Changer la règle" (ne devrait pas arriver pour un Flow
    "regle_non_appliquee", qui suppose justement une décision explicite -- filet de sécurité).
    """
    return (
        session.query(FlowValidationHistory)
        .filter(FlowValidationHistory.flow_id == flow.id, FlowValidationHistory.justification.isnot(None))
        .order_by(FlowValidationHistory.created_at.desc())
        .first()
    )

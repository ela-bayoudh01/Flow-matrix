"""Applique une décision de validation humaine sur un Flow et trace le changement dans
FlowValidationHistory (qui, quand, ancien -> nouveau statut). Les deux écritures sont
toujours faites ensemble : jamais de changement de validation_status sans trace.

Deux chemins bien séparés (décision de conception actée le 2026-09-05, après un test réel où
la détection automatique de contradiction ne déclenchait la fenêtre de confirmation dans
aucun cas concret sur /validation-cycle) :

- `apply_validation` : Valider/Bloquer classique, toujours immédiat, jamais de
  justification ni de `decided_action`. Ne dépend d'aucune détection de contradiction avec
  l'action observée -- un simple clic reste un simple clic, toujours.
- `apply_rule_change` : bouton dédié "Changer la règle", seul chemin qui fige une décision
  CIBLE explicite (`Flow.decided_action`), avec justification obligatoire et une ligne
  d'historique exploitable pour générer la fiche PDF. Voir docs/13-cycle-de-validation.md.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import Flow, FlowValidationHistory, RuleEnforcementClaim
from .time_utils import utcnow

# "Allow" -> "approved", "Block" -> "blocked" -- même mapping que celui utilisé par l'ACL
# Engine pour l'intent "create" (un Flow approuvé formalise un accès en Allow).
STATUS_FOR_ACTION: dict[str, str] = {"Allow": "approved", "Block": "blocked"}


def apply_validation(session: Session, flow: Flow, status: str, validated_by: Optional[str]) -> Flow:
    old_status = flow.validation_status
    flow.validation_status = status
    flow.validated_by = validated_by
    flow.validated_at = utcnow()

    session.add(
        FlowValidationHistory(flow_id=flow.id, old_status=old_status, new_status=status, validated_by=validated_by)
    )

    session.commit()
    session.refresh(flow)
    return flow


def apply_rule_change(
    session: Session,
    flow: Flow,
    target_action: str,
    validated_by: Optional[str],
    justification: str,
) -> Flow:
    new_status = STATUS_FOR_ACTION[target_action]
    old_status = flow.validation_status
    observed_action_before = flow.dominant_action

    flow.validation_status = new_status
    flow.validated_by = validated_by
    flow.validated_at = utcnow()
    flow.decided_action = target_action

    # Une réclamation "Règle non appliquée" déjà en cours (app/rule_enforcement_claims.py)
    # portait sur l'ANCIENNE decided_action -- plus valide dès qu'une nouvelle décision la
    # remplace, jamais laissée à tort "en cours" pour une cible qui n'existe plus (2026-09-10).
    session.query(RuleEnforcementClaim).filter(RuleEnforcementClaim.flow_id == flow.id).delete()

    session.add(
        FlowValidationHistory(
            flow_id=flow.id,
            old_status=old_status,
            new_status=new_status,
            validated_by=validated_by,
            justification=justification,
            observed_action_before=observed_action_before,
            decided_action=target_action,
        )
    )

    session.commit()
    session.refresh(flow)
    return flow

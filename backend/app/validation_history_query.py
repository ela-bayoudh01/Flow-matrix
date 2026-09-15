"""Consultation de FlowValidationHistory (décision sur un flux précis) ET de NetworkPolicy
(décision sur un sous-réseau entier), fusionnées en un seul flux trié par date -- la page
"Historique des validations" doit montrer TOUTES les vraies décisions prises dans l'outil, pas
seulement celles qui portent sur un Flow individuel (2026-09-13, demande de l'encadrant après
démo : "une politique de sous-réseau est aussi une vraie décision à tracer").

Fusion faite ICI, en Python, avant pagination -- jamais paginer chacune des deux sources
séparément puis les recoller côté frontend : la page affichée ne serait plus garantie être "les
N décisions les plus récentes, tous types confondus" dès que l'une des deux dépasse l'autre en
volume, et le regroupement par jour de HistoryPage.tsx (qui suppose une liste déjà triée
globalement) casserait. Même ordre de grandeur de calcul que
Services/validation_cycle_engine.py::compute_diff (requêtes filtrées + fusion/tri en Python),
déjà accepté dans ce projet.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .models import Flow, FlowValidationHistory, NetworkPolicy
from .search_utils import apply_keyword_search

# Type de changement (2026-09-12, demande de l'encadrant) -- distingue une décision "Changer
# la règle" (justification obligatoire, cf. RuleChangeUpdate) d'un Valider/Bloquer classique
# (justification toujours NULL, cf. flow_validation.apply_validation) -- même distinction déjà
# utilisée par la colonne "Fiche" de HistoryPage.tsx (bouton affiché seulement si
# justification non NULL), pas une nouvelle notion inventée ici. PROPRE au flux -- une
# NetworkPolicy n'est ni l'une ni l'autre, cf. list_validation_history ci-dessous.
CHANGE_TYPES = ("rule_change", "classic")

# Type d'entrée (2026-09-13, demande de l'encadrant) -- filtre indépendant du badge visuel
# "Flux"/"Sous-réseau" affiché sur chaque ligne : utile pour isoler uniquement les politiques
# de sous-réseau ou uniquement les décisions de flux, sans changer l'affichage groupé par défaut.
ENTRY_TYPES = ("flow", "network_policy")

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

# Colonnes cherchées par la barre de recherche par mot-clé (demande de l'encadrant,
# 2026-08-25) -- mélange History (old_status/new_status/validated_by) et Flow (contexte
# affiché : src/dst/port/protocole/source), jamais une deuxième liste par ailleurs.
SEARCH_COLUMNS = [
    Flow.source, Flow.src_ip, Flow.dst_ip, Flow.dst_port, Flow.protocol,
    FlowValidationHistory.old_status, FlowValidationHistory.new_status, FlowValidationHistory.validated_by,
]

# Équivalent pour une NetworkPolicy -- mêmes idées (contexte réseau + qui a décidé), colonnes
# différentes puisque l'entité n'a ni src/dst_ip précis ni old/new_status.
POLICY_SEARCH_COLUMNS = [
    NetworkPolicy.source, NetworkPolicy.src_cidr, NetworkPolicy.destination, NetworkPolicy.decided_by,
]


def _list_flow_entries(
    session: Session, *, flow_id: Optional[int], q: Optional[str], source: Optional[str],
    date_from: Optional[datetime], date_to: Optional[datetime], change_type: Optional[str],
) -> list[dict]:
    query = apply_keyword_search(
        session.query(FlowValidationHistory, Flow).join(Flow, FlowValidationHistory.flow_id == Flow.id), q, SEARCH_COLUMNS
    )
    if flow_id is not None:
        query = query.filter(FlowValidationHistory.flow_id == flow_id)
    if source is not None:
        query = query.filter(Flow.source == source)
    if date_from is not None:
        query = query.filter(FlowValidationHistory.created_at >= date_from)
    if date_to is not None:
        # Inclusif jusqu'à la fin de la journée -- date_to arrive typiquement comme une date
        # sans heure (<input type="date"> côté frontend, HistoryPage.tsx), minuit du jour choisi.
        query = query.filter(FlowValidationHistory.created_at < date_to + timedelta(days=1))
    if change_type == "rule_change":
        query = query.filter(FlowValidationHistory.justification.isnot(None))
    elif change_type == "classic":
        query = query.filter(FlowValidationHistory.justification.is_(None))

    return [
        {
            "entry_type": "flow",
            "id": history.id,
            "created_at": history.created_at,
            "source": flow.source,
            "decided_by": history.validated_by,
            "justification": history.justification,
            "flow_id": history.flow_id,
            "src_ip": flow.src_ip,
            "dst_ip": flow.dst_ip,
            "dst_port": flow.dst_port,
            "protocol": flow.protocol,
            "old_status": history.old_status,
            "new_status": history.new_status,
            "observed_action_before": history.observed_action_before,
            "decided_action": history.decided_action,
        }
        for history, flow in query.all()
    ]


def _list_network_policy_entries(
    session: Session, *, q: Optional[str], source: Optional[str],
    date_from: Optional[datetime], date_to: Optional[datetime],
) -> list[dict]:
    query = apply_keyword_search(session.query(NetworkPolicy), q, POLICY_SEARCH_COLUMNS)
    if source is not None:
        query = query.filter(NetworkPolicy.source == source)
    if date_from is not None:
        query = query.filter(NetworkPolicy.created_at >= date_from)
    if date_to is not None:
        query = query.filter(NetworkPolicy.created_at < date_to + timedelta(days=1))

    return [
        {
            "entry_type": "network_policy",
            "id": policy.id,
            "created_at": policy.created_at,
            "source": policy.source,
            "decided_by": policy.decided_by,
            "justification": policy.justification,
            "src_cidr": policy.src_cidr,
            "destination": policy.destination,
            "protocol": policy.protocol,
            "dst_port": policy.dst_port,
            "action": policy.action,
        }
        for policy in query.all()
    ]


def list_validation_history(
    session: Session,
    *,
    flow_id: Optional[int] = None,
    q: Optional[str] = None,
    source: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    change_type: Optional[str] = None,
    entry_type: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    if change_type is not None and change_type not in CHANGE_TYPES:
        raise ValueError(f"change_type inconnu : {change_type!r}. Valeurs possibles : {sorted(CHANGE_TYPES)}")
    if entry_type is not None and entry_type not in ENTRY_TYPES:
        raise ValueError(f"entry_type inconnu : {entry_type!r}. Valeurs possibles : {sorted(ENTRY_TYPES)}")

    entries: list[dict] = []

    if entry_type in (None, "flow"):
        entries += _list_flow_entries(
            session, flow_id=flow_id, q=q, source=source, date_from=date_from, date_to=date_to, change_type=change_type,
        )

    # change_type/flow_id sont des concepts PROPRES au flux -- une NetworkPolicy n'a ni l'un ni
    # l'autre, exclue automatiquement plutôt que silencieusement mélangée à un filtre qui ne
    # s'applique pas à elle.
    if entry_type in (None, "network_policy") and change_type is None and flow_id is None:
        entries += _list_network_policy_entries(session, q=q, source=source, date_from=date_from, date_to=date_to)

    entries.sort(key=lambda e: e["created_at"], reverse=True)

    total_count = len(entries)
    limit = max(1, min(limit, MAX_LIMIT))
    page = entries[offset : offset + limit]
    return {"items": page, "total_count": total_count}

"""Pagination/filtrage de la liste de Flow avec écart (diff_status) par rapport au dernier
ValidationCycle -- même rôle que flows_query.py pour la table plate, mais pour la page
"Cycle de validation". Le diff est calculé en Python sur l'ensemble des Flow correspondant
aux filtres simples (Services/validation_cycle_engine.compute_diff), puis paginé ici -- pas
filtrable en SQL puisque diff_status est une valeur dérivée, pas une colonne Flow. Volume
actuel (43 000 Flow) largement dans la marge déjà validée par qualify_all() (boucle Python
complète sur tous les Flow) -- à revoir si le volume grossit d'un ordre de grandeur.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .flow_filters import FILTER_COLUMNS
from .Services import validation_cycle_engine

MAX_LIMIT = 1000
DEFAULT_LIMIT = 200


def list_flows_with_diff(
    session: Session,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    diff_status: Optional[str] = None,
    q: Optional[str] = None,
    src_cidr: Optional[str] = None,
    dimension: Optional[str] = None,
    row_value: Optional[str] = None,
    col_value: Optional[str] = None,
    **filters,
) -> dict:
    unknown = set(filters) - set(FILTER_COLUMNS)
    if unknown:
        raise ValueError(f"Filtre(s) inconnu(s) : {sorted(unknown)}")
    if diff_status is not None and diff_status not in validation_cycle_engine.DIFF_STATUSES:
        raise ValueError(f"diff_status inconnu : {diff_status!r}. Valeurs possibles : {sorted(validation_cycle_engine.DIFF_STATUSES)}")

    # src_cidr (2026-09-11) : filtre additionnel optionnel, restreint le diff aux Flow dont
    # src_ip tombe dans ce réseau -- utilisé par le "+" d'une ligne de sous-réseau sur la page
    # Cycle de validation (voir Services/validation_cycle_engine.py::compute_diff). Absent par
    # défaut -> comportement inchangé pour tous les appelants existants.
    # dimension/row_value/col_value (2026-09-12) : restreint à une cellule de la Matrice
    # Réelle -- colonne "Écart" du tiroir de détail en mode "Colorer par écart".
    pairs, summary, cycles_by_source = validation_cycle_engine.compute_diff(
        session, filters, q, src_cidr, dimension=dimension, row_value=row_value, col_value=col_value,
    )

    if diff_status is not None:
        pairs = [(flow, diff) for flow, diff in pairs if diff["status"] == diff_status]

    total_count = len(pairs)
    limit = max(1, min(limit, MAX_LIMIT))
    page = pairs[offset : offset + limit]

    items = [{"flow": flow, "diff_status": diff["status"], "diff_details": diff["details"]} for flow, diff in page]
    return {"items": items, "total_count": total_count, "summary": summary, "cycles": cycles_by_source}

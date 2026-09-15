"""Requête filtrée sur les Flow. Utilisée à la fois par la vue "table plate" et par le
drill-down d'une cellule de matrice (même endpoint, filtres différents -- cf. docs/00 §3ter :
les deux vues doivent rester cohérentes puisqu'elles lisent la même source de vérité).
"""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from .flow_filters import FILTER_COLUMNS, FLOW_SEARCH_COLUMNS, apply_filters
from .models import Flow, LogEntry
from .search_utils import apply_keyword_search
from .Services import matrix_engine

MAX_LIMIT = 1000
DEFAULT_LIMIT = 200


def list_known_sources(session: Session) -> list[str]:
    """Toutes les sources (firewalls/sites) qui existent dans le système, triées -- utilisé
    par le sélecteur "Source (firewall)" partagé (useSourceOptions.ts, frontend).

    2026-09-12, bug réel corrigé, signalé juste après une clôture de cycle : `useSourceOptions`
    dérivait auparavant sa liste de `GET /api/matrix?dimension=source_zone`
    (Services/matrix_engine.py::build_matrix), qui exclut désormais les Flow inactifs depuis
    la dernière clôture (`cycle_occurrence_count > 0`, correctif du même jour). Une source
    dont TOUS les flux venaient d'être clôturés (aucun nouvel import depuis) disparaissait
    donc entièrement du sélecteur -- impossible de choisir sa propre Matrice Validée ou de
    préparer son prochain cycle juste après l'action normale de clôturer. Requête dédiée,
    volontairement indépendante de toute notion de cycle : une source existe dès qu'elle a au
    moins un Flow, point final -- jamais un SELECT filtré par `cycle_occurrence_count`.
    """
    rows = session.query(Flow.source).filter(Flow.source.isnot(None)).distinct().all()
    return sorted(source for (source,) in rows)


def list_source_coverage(session: Session) -> list[dict]:
    """Pour chaque source connue : période couverte par ses Flow (`first_seen_at` le plus
    ancien -> `last_seen_at` le plus récent) et date du dernier import -- 2026-09-12, demande
    de l'encadrant après démo (Dashboard par source, indications temporelles sur Matrice/
    Table des flux). Une seule requête, réutilisée telle quelle par les trois pages -- jamais
    trois calculs différents susceptibles de diverger.

    `last_imported_at` vient de `LogEntry.ingested_at` (horodatage serveur posé à
    l'ingestion, cf. models.py::LogEntry), pas de `ImportLog.source` -- ce dernier concatène
    les sources en une seule chaîne quand un fichier en contient plusieurs (rare), compliquant
    inutilement le rapprochement par source exacte alors que LogEntry porte déjà `source`
    directement, une ligne par ligne de log réellement ingérée.
    """
    flow_rows = (
        session.query(
            Flow.source,
            func.min(Flow.first_seen_at),
            func.max(Flow.last_seen_at),
            func.count(Flow.id),
        )
        .filter(Flow.source.isnot(None))
        .group_by(Flow.source)
        .all()
    )
    last_imported_by_source: dict[str, object] = dict(
        session.query(LogEntry.source, func.max(LogEntry.ingested_at))
        .filter(LogEntry.source.isnot(None))
        .group_by(LogEntry.source)
        .all()
    )

    items = [
        {
            "source": source,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "last_imported_at": last_imported_by_source.get(source),
            "flow_count": flow_count,
        }
        for source, first_seen_at, last_seen_at, flow_count in flow_rows
    ]
    items.sort(key=lambda item: item["source"])
    return items


def list_flows(
    session: Session,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    dimension: Optional[str] = None,
    row_value: Optional[str] = None,
    col_value: Optional[str] = None,
    q: Optional[str] = None,
    **filters,
) -> dict:
    unknown = set(filters) - set(FILTER_COLUMNS)
    if unknown:
        raise ValueError(f"Filtre(s) inconnu(s) : {sorted(unknown)}")

    base_query = apply_keyword_search(
        apply_cell_filter(apply_filters(session.query(Flow), filters), dimension, row_value, col_value),
        q, FLOW_SEARCH_COLUMNS,
    )

    total_count = base_query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = base_query.order_by(Flow.id).offset(offset).limit(limit).all()

    summary = _summarize(session, filters, dimension, row_value, col_value, q)
    return {"items": items, "total_count": total_count, "summary": summary}


def apply_cell_filter(query: Query, dimension: Optional[str], row_value: Optional[str], col_value: Optional[str]) -> Query:
    """Restreint aux Flow d'une cellule de matrice précise -- drill-down au clic sur une
    cellule, pour n'importe quelle dimension (pas seulement "zone" comme avant l'extension
    du Matrix Engine, cf. docs/05-matrix-engine.md). Les trois paramètres vont ensemble ou
    pas du tout : row_value/col_value seuls sans dimension ne veulent rien dire.

    `Flow.cycle_occurrence_count > 0` (2026-09-12, bug réel corrigé, signalé en testant le
    correctif du Matrix Engine) : la cellule elle-même (Services/matrix_engine.py::
    build_matrix, corrigé le même jour) exclut déjà les Flow inactifs depuis la dernière
    clôture de cycle -- sans ce même filtre ici, cliquer sur une cellule affichant "4"
    ouvrait un tiroir listant les 6464 flux historiques de la combinaison, pas seulement les
    4 actifs ce cycle. La Table des flux (dimension=None) n'est jamais concernée, reste
    lifetime comme avant.

    Public (pas de préfixe `_`) : réutilisée telle quelle par
    Services/validation_cycle_engine.py::compute_diff (2026-09-12, colonne "Écart" du tiroir
    de détail de la Matrice Réelle en mode "Colorer par écart") -- même filtre de cellule,
    jamais une deuxième logique susceptible de diverger.
    """
    if dimension is None:
        return query
    if row_value is None or col_value is None:
        raise ValueError("dimension fourni sans row_value/col_value -- les trois vont ensemble")
    return query.filter(matrix_engine.cell_filter(dimension, row_value, col_value), Flow.cycle_occurrence_count > 0)


def _summarize(
    session: Session,
    filters: dict,
    dimension: Optional[str] = None,
    row_value: Optional[str] = None,
    col_value: Optional[str] = None,
    q: Optional[str] = None,
) -> dict:
    action_query = apply_keyword_search(
        apply_cell_filter(
            apply_filters(session.query(Flow.dominant_action, func.count(Flow.id)), filters), dimension, row_value, col_value
        ),
        q, FLOW_SEARCH_COLUMNS,
    ).group_by(Flow.dominant_action)
    action_counts: dict[Optional[str], int] = dict(action_query.all())
    # un Flow "Mixed" compte à la fois dans allow et block : c'est bien un flux qui a été
    # à la fois autorisé et bloqué au moins une fois, les deux infos sont pertinentes.
    allow_count = action_counts.get("Allow", 0) + action_counts.get("Mixed", 0)
    block_count = action_counts.get("Block", 0) + action_counts.get("Mixed", 0)

    criticality_query = apply_keyword_search(
        apply_cell_filter(
            apply_filters(session.query(Flow.criticality_label, func.count(Flow.id)), filters), dimension, row_value, col_value
        ),
        q, FLOW_SEARCH_COLUMNS,
    ).group_by(Flow.criticality_label)
    criticality_breakdown = {(label or "non_qualifie"): count for label, count in criticality_query.all()}

    return {
        "total_flows": sum(action_counts.values()),
        "allow_count": allow_count,
        "block_count": block_count,
        "criticality_breakdown": criticality_breakdown,
    }

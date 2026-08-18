"""Matrix Engine : construit une vue croisée dynamique à partir des Flow -- jamais de
table persistée (principe acté dans docs/00 §3ter : la matrice est une vue de synthèse,
recalculée à chaque appel, pas une nouvelle source de vérité).

La dimension de regroupement (lignes/colonnes) est paramétrable via DIMENSIONS ci-dessous.
Zone x Zone est le choix de départ (validé par Loulou le 2026-08-11), mais reste provisoire.
Extension 2026-08-13 (encadrant validé) : exploiter au maximum les champs déjà disponibles
sur Flow plutôt qu'une seule vue -- ~14 dimensions, dont 3 dérivées (voir DERIVED_FIELDS)
qui réutilisent des classifications déjà prouvées ailleurs (ZONE_ROLES, SENSITIVE_PORTS du
Qualification Engine) plutôt que d'inventer une nouvelle logique. Ajouter une dimension =
ajouter une entrée dans DIMENSIONS (+ une expression dans _axis_expression si dérivée),
rien d'autre à changer dans la logique d'agrégation -- confirmé une nouvelle fois ici.
"""

from typing import Optional

from sqlalchemy import Integer, String, and_, case, cast, func, literal
from sqlalchemy.orm import Session

from ..flow_filters import FILTER_COLUMNS, apply_filters
from ..models import Flow
from .qualification_engine import COMMON_SAFE_PORTS, SENSITIVE_PORTS, UNCLASSIFIED_ROLE, ZONE_ROLES
from .recommendation_engine import MIN_OBSERVATION_WINDOW_DAYS

DIMENSIONS: dict[str, tuple[str, str]] = {
    "zone": ("ingress_zone", "egress_zone"),
    "ip": ("src_ip", "dst_ip"),
    "source_zone": ("source", "egress_zone"),
    "zone_application": ("ingress_zone", "application_protocol"),
    "zone_protocol": ("ingress_zone", "protocol"),
    "zone_port": ("ingress_zone", "dst_port"),
    "zone_action": ("ingress_zone", "dominant_action"),
    "zone_rule": ("ingress_zone", "last_access_control_rule_name"),
    "zone_criticality": ("ingress_zone", "criticality_label"),
    "zone_validation": ("ingress_zone", "validation_status"),
    "source_criticality": ("source", "criticality_label"),
    "direction_criticality": ("direction", "criticality_label"),
    "port_category_zone": ("port_category", "ingress_zone"),
    "timeslot_zone": ("timeslot", "ingress_zone"),
}
DEFAULT_DIMENSION = "zone"

# Dimensions dérivées (pas une colonne Flow directe -- une expression SQL calculée à la
# volée, cf. _axis_expression). Réutilisent une classification déjà prouvée ailleurs dans le
# projet plutôt que d'en inventer une nouvelle :
# - "direction" : ZONE_ROLES (Qualification Engine, docs/07) -- interne/externe par zone.
# - "port_category" : SENSITIVE_PORTS/COMMON_SAFE_PORTS (Qualification Engine, docs/07).
DERIVED_FIELDS = {"direction", "port_category", "timeslot"}

# Dimensions dont le résultat n'est fiable qu'au-delà d'une fenêtre d'observation minimale
# (même seuil et même logique que la garde "obsolete" du Recommendation Engine, docs/09 --
# réutilisé ici tel quel, pas redéfini, cf. dimension_notice ci-dessous).
TIME_GATED_DIMENSIONS = {"timeslot_zone"}

# Mesuré sur flow_matrix.db réel (2026-08-13) : "ip" est le seul cas hors norme, ~1s et
# 31 050 cellules contre 0,1-0,25s et moins de 65 cellules pour les 13 autres dimensions --
# pas un problème de lenteur serveur en soi, mais un volume difficilement exploitable sans
# filtre. Seuil générique (pas seulement pour "ip") : n'importe quelle dimension future avec
# la même caractéristique héritera du même avertissement sans code dédié.
LARGE_RESULT_CELL_THRESHOLD = 1000

# Valeur affichée quand le champ de regroupement est absent sur un Flow (ex. certains
# événements ICMP dérivés n'ont pas de zone dans le log source -- cas réel confirmé,
# cf. docs/01-journal-technique.md, addendum étape 5). La cellule reste comptée et
# cliquable : jamais masquée, seulement étiquetée explicitement.
UNSET_LABEL = "(Non renseigné)"


def build_matrix(session: Session, dimension: str = DEFAULT_DIMENSION, **filters) -> dict:
    """Retourne {"cells": [...], "notice": str | None} pour la dimension et les filtres
    donnés. Ne modifie rien, ne persiste rien -- recalculée à chaque appel.

    `filters` accepte exactement les mêmes clés que `flows_query.list_flows` (même
    définition partagée, `flow_filters.FILTER_COLUMNS`) -- y compris `ingress_zone`/
    `egress_zone`, qui, en dimension "zone", restreignent naturellement la matrice à une
    seule ligne/colonne plutôt que de nécessiter un filtrage séparé côté frontend : le
    calcul est refait avec le filtre appliqué, pas juste caché après coup (sinon les totaux
    affichés seraient faux).
    """
    if dimension not in DIMENSIONS:
        raise ValueError(f"Dimension inconnue : {dimension!r}. Valeurs possibles : {sorted(DIMENSIONS)}")
    unknown = set(filters) - set(FILTER_COLUMNS)
    if unknown:
        raise ValueError(f"Filtre(s) inconnu(s) : {sorted(unknown)}")

    row_field, col_field = DIMENSIONS[dimension]
    row_col = axis_expression(row_field).label("row")
    col_col = axis_expression(col_field).label("col")

    counts_query = apply_filters(
        session.query(
            row_col,
            col_col,
            func.count(Flow.id).label("flow_count"),
            func.coalesce(func.sum(Flow.allow_count), 0).label("allow_count"),
            func.coalesce(func.sum(Flow.block_count), 0).label("block_count"),
            func.coalesce(func.sum(Flow.total_initiator_bytes + Flow.total_responder_bytes), 0).label("total_bytes"),
            func.coalesce(func.sum(Flow.total_connection_duration), 0).label("total_duration_seconds"),
        ),
        filters,
    ).group_by(row_col, col_col)

    criticality_query = apply_filters(
        session.query(
            row_col,
            col_col,
            Flow.criticality_label.label("criticality_label"),
            func.count(Flow.id).label("count"),
        ),
        filters,
    ).group_by(row_col, col_col, Flow.criticality_label)

    criticality_by_cell: dict[tuple, dict] = {}
    for row in criticality_query.all():
        label = row.criticality_label or "non_qualifie"
        criticality_by_cell.setdefault((row.row, row.col), {})[label] = row.count

    cells = []
    for row in counts_query.all():
        # str() : certains axes (ex. "zone_port", dst_port) sont des entiers en base --
        # MatrixCell.row/col est une étiquette de regroupement affichable, jamais utilisée
        # pour un calcul, donc toujours une chaîne en sortie, quel que soit le type source.
        cells.append(
            {
                "row": str(row.row) if row.row is not None else UNSET_LABEL,
                "col": str(row.col) if row.col is not None else UNSET_LABEL,
                "flow_count": row.flow_count,
                "allow_count": row.allow_count,
                "block_count": row.block_count,
                "total_bytes": row.total_bytes,
                "total_duration_seconds": row.total_duration_seconds,
                "criticality_breakdown": criticality_by_cell.get((row.row, row.col), {}),
            }
        )

    notice = _dimension_notice(session, dimension, filters, len(cells))
    return {"cells": cells, "notice": notice}


def axis_expression(field_name: str):
    """Une colonne Flow directe (cas courant), ou l'expression SQL d'un champ dérivé.
    Public (pas de préfixe `_`) : réutilisé par flows_query.py pour que le drill-down d'une
    cellule fonctionne pour n'importe quelle dimension, pas seulement "zone" -- même
    expression exacte que celle utilisée pour construire la cellule, jamais une deuxième
    logique susceptible de diverger.
    """
    if field_name == "direction":
        return _direction_expression()
    if field_name == "port_category":
        return _port_category_expression()
    if field_name == "timeslot":
        return _timeslot_expression()
    return getattr(Flow, field_name)


def cell_filter(dimension: str, row_value: str, col_value: str):
    """Condition SQLAlchemy identifiant les Flow d'une cellule précise (row_value, col_value)
    d'une matrice -- réutilisée par flows_query.list_flows pour le drill-down au clic sur une
    cellule. cast(..., String) : row_value/col_value sont toujours des chaînes côté API (cf.
    str() dans build_matrix), y compris pour des axes numériques comme "zone_port" (dst_port
    est un entier en base) -- comparer les deux côtés en texte évite un mauvais typage.
    """
    if dimension not in DIMENSIONS:
        raise ValueError(f"Dimension inconnue : {dimension!r}. Valeurs possibles : {sorted(DIMENSIONS)}")
    row_field, col_field = DIMENSIONS[dimension]
    row_expr = cast(axis_expression(row_field), String)
    col_expr = cast(axis_expression(col_field), String)
    return and_(row_expr == row_value, col_expr == col_value)


def _zone_role_expression(zone_column):
    # Même classification que Qualification Engine._score_zone (docs/07) -- ZONE_ROLES
    # prouvée sur les 11 zones réelles, jamais redéfinie ici.
    internal_zones = tuple(z for z, role in ZONE_ROLES.items() if role == "interne")
    external_zones = tuple(z for z, role in ZONE_ROLES.items() if role == "externe")
    return case(
        (zone_column.in_(internal_zones), literal("interne")),
        (zone_column.in_(external_zones), literal("externe")),
        else_=literal(UNCLASSIFIED_ROLE),
    )


def _direction_expression():
    # Même convention de nommage que qualification_engine._score_zone
    # (f"{ingress_role}_vers_{egress_role}") -- cohérence volontaire entre les deux moteurs.
    return _zone_role_expression(Flow.ingress_zone).concat(literal("_vers_")).concat(
        _zone_role_expression(Flow.egress_zone)
    )


def _port_category_expression():
    # Mêmes catégories/valeurs que Qualification Engine._score_port (docs/07) -- un port
    # NULL (33 cas réels observés) tombe dans "port_non_classifie", jamais une erreur.
    return case(
        (Flow.dst_port.in_(tuple(SENSITIVE_PORTS)), literal("port_sensible")),
        (Flow.dst_port.in_(tuple(COMMON_SAFE_PORTS)), literal("port_courant")),
        else_=literal("port_non_classifie"),
    )


def _timeslot_expression():
    # Créneaux de 6h sur l'heure de first_seen_at (canonique, cf. docs/03-parser-engine.md).
    # strftime() est spécifique SQLite -- couplage assumé, cohérent avec le reste du projet
    # (SQLite scope V1, cf. docs/00 §5). NULL explicite (jamais absorbé dans un créneau au
    # hasard) plutôt que de laisser le cas NULL retomber silencieusement dans le else_.
    hour = cast(func.strftime("%H", Flow.first_seen_at), Integer)
    return case(
        (Flow.first_seen_at.is_(None), literal(UNSET_LABEL)),
        (hour < 6, literal("00h-06h")),
        (hour < 12, literal("06h-12h")),
        (hour < 18, literal("12h-18h")),
        else_=literal("18h-24h"),
    )


def _dimension_notice(session: Session, dimension: str, filters: dict, cell_count: int) -> Optional[str]:
    """Avertissement générique attaché à une dimension quand les données actuelles ne
    permettent pas un résultat fiable ou facilement exploitable -- jamais un résultat caché
    ou trompeur, toujours affiché avec la matrice telle quelle. Pattern déjà appliqué une
    première fois pour "obsolete" dans le Recommendation Engine (docs/09) ; généralisé ici à
    deux causes (fenêtre d'observation courte, volume de cellules) pour être réutilisable par
    n'importe quelle dimension future ayant l'une ou l'autre contrainte.
    """
    notices = []

    if dimension in TIME_GATED_DIMENSIONS:
        window_query = apply_filters(
            session.query(func.min(Flow.first_seen_at), func.max(Flow.last_seen_at)), filters
        )
        min_at, max_at = window_query.one()
        window_days = (max_at - min_at).total_seconds() / 86400 if min_at and max_at else None

        if window_days is None or window_days < MIN_OBSERVATION_WINDOW_DAYS:
            observed = f"{window_days:.1f}" if window_days is not None else "0"
            notices.append(
                f"Fenêtre d'observation actuelle : {observed} jour(s) -- en dessous du seuil de "
                f"fiabilité ({MIN_OBSERVATION_WINDOW_DAYS} jours) pour cette dimension."
            )

    if cell_count > LARGE_RESULT_CELL_THRESHOLD:
        notices.append(
            f"{cell_count} cellules -- volume élevé, combine avec un filtre (zone, source...) "
            "pour une vue plus exploitable."
        )

    return " ".join(notices) if notices else None

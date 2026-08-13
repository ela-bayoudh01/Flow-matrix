"""Matrix Engine : construit une vue croisée dynamique à partir des Flow -- jamais de
table persistée (principe acté dans docs/00 §3ter : la matrice est une vue de synthèse,
recalculée à chaque appel, pas une nouvelle source de vérité).

La dimension de regroupement (lignes/colonnes) est paramétrable via DIMENSIONS ci-dessous.
Zone x Zone est le choix de départ (validé par Loulou le 2026-08-11 sur la base de la
cardinalité réelle : 11 zones vs 100 IP sources / 5827 IP destinations), mais reste
provisoire -- à confirmer avec son encadrant, qui pourra demander un regroupement différent.
Ajouter une nouvelle dimension = ajouter une entrée dans DIMENSIONS, rien d'autre à changer
dans la logique d'agrégation.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..flow_filters import FILTER_COLUMNS, apply_filters
from ..models import Flow

DIMENSIONS: dict[str, tuple[str, str]] = {
    "zone": ("ingress_zone", "egress_zone"),
    "ip": ("src_ip", "dst_ip"),
}
DEFAULT_DIMENSION = "zone"

# Valeur affichée quand le champ de regroupement est absent sur un Flow (ex. certains
# événements ICMP dérivés n'ont pas de zone dans le log source -- cas réel confirmé,
# cf. docs/01-journal-technique.md, addendum étape 5). La cellule reste comptée et
# cliquable : jamais masquée, seulement étiquetée explicitement.
UNSET_LABEL = "(Non renseigné)"


def build_matrix(session: Session, dimension: str = DEFAULT_DIMENSION, **filters) -> list[dict]:
    """Retourne la liste des cellules (row, col) agrégées à partir des Flow correspondant
    aux filtres. Ne modifie rien, ne persiste rien -- recalculée à chaque appel.

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
    row_col = getattr(Flow, row_field)
    col_col = getattr(Flow, col_field)

    counts_query = apply_filters(
        session.query(
            row_col.label("row"),
            col_col.label("col"),
            func.count(Flow.id).label("flow_count"),
            func.coalesce(func.sum(Flow.allow_count), 0).label("allow_count"),
            func.coalesce(func.sum(Flow.block_count), 0).label("block_count"),
            func.coalesce(func.sum(Flow.total_initiator_bytes + Flow.total_responder_bytes), 0).label("total_bytes"),
        ),
        filters,
    ).group_by(row_col, col_col)

    criticality_query = apply_filters(
        session.query(
            row_col.label("row"),
            col_col.label("col"),
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
        cells.append(
            {
                "row": row.row if row.row is not None else UNSET_LABEL,
                "col": row.col if row.col is not None else UNSET_LABEL,
                "flow_count": row.flow_count,
                "allow_count": row.allow_count,
                "block_count": row.block_count,
                "total_bytes": row.total_bytes,
                "criticality_breakdown": criticality_by_cell.get((row.row, row.col), {}),
            }
        )
    return cells

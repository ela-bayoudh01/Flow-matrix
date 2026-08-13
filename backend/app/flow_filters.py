"""Filtres sur Flow, partagés entre flows_query.py (table plate) et Services/matrix_engine.py
(matrice) -- une seule définition pour garantir que les deux vues acceptent exactement les
mêmes filtres, cohérent avec le principe déjà acté (docs/00 §3ter : les deux vues doivent
rester cohérentes puisqu'elles lisent la même source de vérité).
"""

from typing import Optional

from sqlalchemy.orm import Query

from .models import Flow

FILTER_COLUMNS = {
    "source": Flow.source,
    "ingress_zone": Flow.ingress_zone,
    "egress_zone": Flow.egress_zone,
    "src_ip": Flow.src_ip,
    "dst_ip": Flow.dst_ip,
    "protocol": Flow.protocol,
    "dst_port": Flow.dst_port,
    "dominant_action": Flow.dominant_action,
    "validation_status": Flow.validation_status,
    "criticality_label": Flow.criticality_label,
    "application_protocol": Flow.application_protocol,
    "web_application": Flow.web_application,
}


def apply_filters(query: Query, filters: dict) -> Query:
    for key, column in FILTER_COLUMNS.items():
        value = filters.get(key)
        if value is not None:
            query = query.filter(column == value)
    return query


def flow_filter_params(
    source: Optional[str] = None,
    ingress_zone: Optional[str] = None,
    egress_zone: Optional[str] = None,
    src_ip: Optional[str] = None,
    dst_ip: Optional[str] = None,
    protocol: Optional[str] = None,
    dst_port: Optional[int] = None,
    dominant_action: Optional[str] = None,
    validation_status: Optional[str] = None,
    criticality_label: Optional[str] = None,
    application_protocol: Optional[str] = None,
    web_application: Optional[str] = None,
) -> dict:
    """Dépendance FastAPI (`Depends`) : les query params de filtrage, communs à
    GET /api/flows et GET /api/matrix -- une seule signature, jamais de divergence entre
    les filtres acceptés par les deux endpoints.
    """
    return {k: v for k, v in locals().items() if v is not None}

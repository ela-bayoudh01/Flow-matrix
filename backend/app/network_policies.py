"""Politiques de sous-réseau (2026-09-10, demande de l'encadrant) -- fonctionnalité NOUVELLE et
VOLONTAIREMENT ISOLÉE : aucun lien avec Flow.decided_action, le diff de cycle, FlowSnapshot, ou
une quelconque logique de correspondance/application automatique aux Flow. Un simple
enregistrement, pour l'instant -- voir models.py::NetworkPolicy.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .models import NetworkPolicy

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def create_network_policy(
    session: Session,
    *,
    source: Optional[str],
    src_cidr: str,
    destination: str,
    protocol: Optional[str],
    dst_port: Optional[int],
    action: str,
    justification: str,
    decided_by: Optional[str],
) -> NetworkPolicy:
    policy = NetworkPolicy(
        source=source,
        src_cidr=src_cidr,
        destination=destination,
        protocol=protocol,
        dst_port=dst_port,
        action=action,
        justification=justification,
        decided_by=decided_by,
    )
    session.add(policy)
    session.commit()
    session.refresh(policy)
    return policy


def list_network_policies(
    session: Session, *, source: Optional[str] = None, limit: int = DEFAULT_LIMIT, offset: int = 0
) -> dict:
    query = session.query(NetworkPolicy)
    if source is not None:
        query = query.filter(NetworkPolicy.source == source)
    query = query.order_by(NetworkPolicy.created_at.desc())

    total_count = query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = query.offset(offset).limit(limit).all()
    return {"items": items, "total_count": total_count}

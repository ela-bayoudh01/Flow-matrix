"""Drill-down des LogEntry individuels d'un Flow (2026-09-06, demande de l'encadrant) --
occurrence_count agrège potentiellement des milliers de connexions (le plus fréquent observé :
3 793 fois, cf. docs/04) sans jamais avoir été consultables une par une jusqu'ici. Liste
paginée, la plus récente en premier -- même convention que validation_history_query.py.
"""

from sqlalchemy.orm import Session

from .models import LogEntry

MAX_LIMIT = 500
DEFAULT_LIMIT = 50


def list_log_entries_for_flow(session: Session, *, flow_id: int, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
    query = session.query(LogEntry).filter(LogEntry.flow_id == flow_id)

    total_count = query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = query.order_by(LogEntry.first_packet_at.desc()).offset(offset).limit(limit).all()

    return {"items": items, "total_count": total_count}

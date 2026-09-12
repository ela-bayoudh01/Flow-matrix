"""Historique des imports (2026-09-11, demande de l'encadrant) -- enregistre le résultat
DÉJÀ CALCULÉ par ingestion.import_log_file() dans la table d'audit ImportLog, en ajout seul.
Aucune logique d'import ici -- ce module ne fait qu'écrire/lire ImportLog, jamais appelé par
app/ingestion.py lui-même (qui reste intégralement inchangé), uniquement par main.py juste
après avoir obtenu le résumé d'un import réussi.
"""

from sqlalchemy.orm import Session

from .models import ImportLog

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def record_import(session: Session, summary: dict) -> ImportLog:
    """`summary` = le dict déjà retourné par ingestion.import_log_file() -- aucun recalcul,
    juste une projection vers les colonnes d'ImportLog. `sources` (liste, un fichier peut en
    théorie contenir plusieurs ACPolicy) concaténées en une seule chaîne lisible."""
    log = ImportLog(
        filename=summary["filename"],
        source=", ".join(summary["sources"]),
        lines_read=summary["lines_read"],
        log_entries_created=summary["log_entries_created"],
        log_entries_skipped_duplicate=summary["log_entries_skipped_duplicate"],
        parsing_errors=summary["parsing_errors"],
        flows_touched=summary["flows_touched"],
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def list_import_logs(session: Session, *, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
    """Du plus récent au plus ancien -- demande explicite de l'encadrant."""
    query = session.query(ImportLog).order_by(ImportLog.imported_at.desc())
    total_count = query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = query.offset(offset).limit(limit).all()
    return {"items": items, "total_count": total_count}

"""Historique des imports (2026-09-11, demande de l'encadrant) -- enregistre le résultat
DÉJÀ CALCULÉ par ingestion.import_log_file() dans la table d'audit ImportLog (+ ImportLogError
depuis le 2026-09-14, une ligne par erreur de parsing), en ajout seul. Aucune logique d'import
ici -- ce module ne fait qu'écrire/lire ces deux tables, jamais appelé par app/ingestion.py
lui-même, uniquement par main.py juste après avoir obtenu le résumé d'un import réussi.
"""

from sqlalchemy.orm import Session

from .models import ImportLog, ImportLogError

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def record_import(session: Session, summary: dict) -> ImportLog:
    """`summary` = le dict déjà retourné par ingestion.import_log_file() -- aucun recalcul,
    juste une projection vers les colonnes d'ImportLog. `sources` (liste, un fichier peut en
    théorie contenir plusieurs ACPolicy) concaténées en une seule chaîne lisible.

    `parsing_error_details` (2026-09-14, demande de l'encadrant : "voir Historique des
    imports pour le détail" ne tenait pas sa promesse, parsing_errors n'était qu'un compteur)
    -- persisté une ligne par erreur (ImportLogError), rattachée à cet ImportLog précis, pour
    juger après coup si une erreur isolée est bénigne ou révèle un vrai problème de format.
    """
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

    error_details = summary.get("parsing_error_details", [])
    if error_details:
        session.add_all(
            ImportLogError(import_log_id=log.id, **detail) for detail in error_details
        )
        session.commit()

    return log


def list_import_logs(session: Session, *, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
    """Du plus récent au plus ancien -- demande explicite de l'encadrant."""
    query = session.query(ImportLog).order_by(ImportLog.imported_at.desc())
    total_count = query.count()
    limit = max(1, min(limit, MAX_LIMIT))
    items = query.offset(offset).limit(limit).all()
    return {"items": items, "total_count": total_count}


def list_import_log_errors(session: Session, import_log_id: int) -> list[ImportLogError]:
    """Détail des lignes en échec d'un import précis, dans l'ordre où elles sont apparues dans
    le fichier -- affiché derrière un clic sur le nombre d'erreurs (ImportPage.tsx)."""
    return (
        session.query(ImportLogError)
        .filter(ImportLogError.import_log_id == import_log_id)
        .order_by(ImportLogError.line_number)
        .all()
    )

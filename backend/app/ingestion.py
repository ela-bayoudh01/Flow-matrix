"""Ingestion : lit un fichier de logs Cisco FTD ligne par ligne, orchestre le Parser
Engine puis le Flow Engine. Ne contient pas leurs règles métier (juste le fait de les
enchaîner), conformément à la séparation actée dans docs/00 §3ter.
"""

import logging
from typing import IO, Iterable

from sqlalchemy.orm import Session

from .models import LogEntry
from .parser import LogParsingError, parse_line
from .Services import flow_engine

logger = logging.getLogger(__name__)


def resolve_source(parsed: dict, filename: str) -> str:
    """source = ACPolicy (donnée du log lui-même). Fallback sur le nom de fichier
    importé si ACPolicy est absent (non observé sur les 183 877 lignes réelles
    analysées, mais à sécuriser) -- décision de Loulou, 2026-08-11.
    """
    ac_policy = parsed.get("ac_policy")
    if ac_policy:
        return ac_policy
    logger.warning(
        "ACPolicy absent sur une ligne de %s : source repliée sur le nom de fichier.",
        filename,
    )
    return filename


def import_log_file(session: Session, file: IO[bytes], filename: str) -> dict:
    # Clé d'idempotence : (source, device_uuid, connection_id, first_packet_at). ConnectionID
    # seul n'est pas stable dans le temps (compteur borné par device, réutilisé -- vu sur
    # données réelles), d'où l'ajout de l'horodatage pour ne pas perdre de vraies connexions.
    existing_keys = {
        (source, uuid, cid, ts)
        for source, uuid, cid, ts in session.query(
            LogEntry.source, LogEntry.device_uuid, LogEntry.connection_id, LogEntry.first_packet_at
        )
    }
    # Capturé AVANT le traitement des lignes : sert uniquement à distinguer une source déjà
    # connue d'une source nouvelle dans le résumé retourné -- pas une nouvelle règle métier,
    # juste exposer une distinction déjà implicite (resolve_source tourne déjà par ligne).
    sources_before_import = {s for (s,) in session.query(LogEntry.source).distinct()}

    lines_read = 0
    parsing_errors = 0
    log_entries_created = 0
    log_entries_skipped_duplicate = 0
    flows_touched = set()
    sources_seen: set[str] = set()
    flow_cache: flow_engine.FlowCache = {}

    for raw_line in _iter_text_lines(file):
        lines_read += 1
        if not raw_line.strip():
            continue

        try:
            parsed = parse_line(raw_line)
        except LogParsingError:
            parsing_errors += 1
            logger.warning("Ligne %d de %s ignorée (parsing) : %r", lines_read, filename, raw_line[:120])
            continue

        source = resolve_source(parsed, filename)
        sources_seen.add(source)
        key = (source, parsed.get("device_uuid"), parsed.get("connection_id"), parsed.get("first_packet_at"))
        if key in existing_keys:
            log_entries_skipped_duplicate += 1
            continue
        existing_keys.add(key)

        log_entry = LogEntry(source=source, **parsed)
        session.add(log_entry)  # pas de flush() ici : l'autoflush de SQLAlchemy suffit
        # avant la requête du Flow Engine juste après, et flow_engine.consolidate() n'a
        # besoin ni de log_entry.id ni de flow.id pour fonctionner correctement.

        flow_engine.consolidate(session, log_entry, flow_cache)
        flows_touched.add((source, log_entry.src_ip, log_entry.dst_ip, log_entry.dst_port, log_entry.protocol))
        log_entries_created += 1

    session.commit()

    new_sources = sources_seen - sources_before_import

    return {
        "filename": filename,
        "lines_read": lines_read,
        "log_entries_created": log_entries_created,
        "log_entries_skipped_duplicate": log_entries_skipped_duplicate,
        "parsing_errors": parsing_errors,
        "flows_touched": len(flows_touched),
        "sources": sorted(sources_seen),
        "new_sources": sorted(new_sources),
    }


def _iter_text_lines(file: IO[bytes]) -> Iterable[str]:
    for raw_line in file:
        if isinstance(raw_line, bytes):
            yield raw_line.decode("utf-8", errors="replace")
        else:
            yield raw_line

"""Flow Engine : consolide les LogEntry en Flow (entité métier centrale). Traduit en
code la transformation documentée dans docs/02-modele-de-donnees.md : conservé tel quel
(clé d'identité), agrégé (compteurs/sommes/min/max), dominant/dernière valeur, dérivé
(dominant_action). Ne fait ni parsing ni qualification ni requête HTTP.
"""

from typing import Optional

from sqlalchemy.orm import Session

from ..models import Flow, LogEntry

FlowCache = dict  # {(source, src_ip, dst_ip, dst_port, protocol): Flow}


def consolidate(session: Session, log_entry: LogEntry, flow_cache: Optional[FlowCache] = None) -> Flow:
    """Rattache log_entry au Flow correspondant (créé si besoin) et met à jour ses
    agrégats. Modifie log_entry.flow en place ; ne commit pas (responsabilité de l'appelant).

    `flow_cache`, si fourni, évite une requête base par ligne pour les flows déjà vus dans le
    même import (un flow observé des milliers de fois ne coûte alors qu'une seule requête,
    au lieu d'une par ligne -- mesuré sur données réelles : facteur déterminant de performance,
    voir docs/01-journal-technique.md, étape 4).
    """
    key = (log_entry.source, log_entry.src_ip, log_entry.dst_ip, log_entry.dst_port, log_entry.protocol)
    flow = flow_cache.get(key) if flow_cache is not None else None

    if flow is None:
        flow = (
            session.query(Flow)
            .filter_by(
                source=log_entry.source,
                src_ip=log_entry.src_ip,
                dst_ip=log_entry.dst_ip,
                dst_port=log_entry.dst_port,
                protocol=log_entry.protocol,
            )
            .first()
        )

    if flow is None:
        # Compteurs initialisés explicitement : mapped_column(default=0) n'est appliqué par
        # SQLAlchemy qu'au flush(), pas à la construction Python -- sans ça, flow.occurrence_count
        # vaudrait None et les += juste après lèveraient une TypeError (bug rencontré ici même).
        flow = Flow(
            source=log_entry.source,
            src_ip=log_entry.src_ip,
            dst_ip=log_entry.dst_ip,
            dst_port=log_entry.dst_port,
            protocol=log_entry.protocol,
            occurrence_count=0,
            allow_count=0,
            block_count=0,
            total_initiator_bytes=0,
            total_responder_bytes=0,
            total_connection_duration=0,
        )
        session.add(flow)
        # Pas de flush() ici : SQLAlchemy résout la relation log_entry.flow -> flow (et la FK
        # associée) au prochain flush/commit, que flow.id soit déjà attribué ou non.

    if flow_cache is not None:
        flow_cache[key] = flow

    flow.occurrence_count += 1
    if log_entry.access_control_rule_action == "Allow":
        flow.allow_count += 1
    elif log_entry.access_control_rule_action == "Block":
        flow.block_count += 1
    flow.dominant_action = _dominant_action(flow.allow_count, flow.block_count)

    flow.total_initiator_bytes += log_entry.initiator_bytes or 0
    flow.total_responder_bytes += log_entry.responder_bytes or 0
    flow.total_connection_duration += log_entry.connection_duration or 0

    # Valeur dominante/dernière observée : mise à jour seulement si cette ligne est la
    # plus récente vue jusqu'ici (par FirstPacketSecond), pas par ordre d'insertion --
    # sinon importer un fichier plus ancien après un plus récent ferait régresser ces champs.
    if log_entry.first_packet_at is not None:
        if flow.first_seen_at is None or log_entry.first_packet_at < flow.first_seen_at:
            flow.first_seen_at = log_entry.first_packet_at
        if flow.last_seen_at is None or log_entry.first_packet_at >= flow.last_seen_at:
            flow.last_seen_at = log_entry.first_packet_at
            flow.ingress_zone = log_entry.ingress_zone
            flow.egress_zone = log_entry.egress_zone
            flow.application_protocol = log_entry.application_protocol
            flow.web_application = log_entry.web_application
            flow.last_access_control_rule_name = log_entry.access_control_rule_name

    log_entry.flow = flow
    return flow


def _dominant_action(allow_count: int, block_count: int) -> str | None:
    if allow_count and block_count:
        return "Mixed"
    if allow_count:
        return "Allow"
    if block_count:
        return "Block"
    return None

"""Parser Engine : transforme une ligne de log syslog Cisco FTD en un dict de champs
prêts à construire un LogEntry (voir docs/02-modele-de-donnees.md pour la cartographie
complète colonne <-> champ Cisco). Fonctions pures : aucun accès base de données, aucune
notion de `source`/`flow_id` ici (assignés par l'appelant lors de l'ingestion).

Format calibré sur 183 877 lignes réelles (docs/01-journal-technique.md, étape 2) :
    <Mon> <D> <HH:MM:SS> <IP_firewall>  : %FTD-<sévérité>-<msgid>: Key1: value1, Key2: value2, ...

Convention de dates : tous les datetime produits ici (et dans tout le projet, voir
database._utcnow) sont **naïfs, en UTC implicite**. SQLite ne conserve pas l'information
de fuseau horaire à travers un aller-retour en base (elle revient toujours naïve) ; mélanger
naïf et "aware" fait lever un TypeError à la comparaison (bug réel rencontré et corrigé à
l'étape ingestion/Flow Engine, cf. docs/01-journal-technique.md).
"""

import re
from datetime import datetime
from typing import Optional

_HEADER_RE = re.compile(r"^(\w+ \d+ \d+:\d+:\d+) (\S+)\s+: (%FTD-\d-\d+): (.*)$")

# Champs texte copiés tels quels vers une colonne LogEntry.
_STRING_FIELDS = {
    "DeviceUUID": "device_uuid",
    "AccessControlRuleAction": "access_control_rule_action",
    "AccessControlRuleName": "access_control_rule_name",
    "ACPolicy": "ac_policy",
    "SrcIP": "src_ip",
    "DstIP": "dst_ip",
    "Protocol": "protocol",
    "IngressZone": "ingress_zone",
    "EgressZone": "egress_zone",
    "ApplicationProtocol": "application_protocol",
    "WebApplication": "web_application",
}

# Champs numériques copiés vers une colonne LogEntry (int).
_INT_FIELDS = {
    "ConnectionID": "connection_id",
    "SrcPort": "src_port",
    "DstPort": "dst_port",
    "ConnectionDuration": "connection_duration",
    "InitiatorPackets": "initiator_packets",
    "ResponderPackets": "responder_packets",
    "InitiatorBytes": "initiator_bytes",
    "ResponderBytes": "responder_bytes",
}

# Toute clé du log non listée ici finit dans `extra` (JSON), sans perte (cf. docs/02).
_STRUCTURED_KEYS = set(_STRING_FIELDS) | set(_INT_FIELDS) | {"FirstPacketSecond"}


class LogParsingError(ValueError):
    """Ligne de log qui ne correspond pas au format Cisco FTD attendu."""


def parse_line(raw_line: str) -> dict:
    line = raw_line.rstrip("\n")
    match = _HEADER_RE.match(line)
    if not match:
        raise LogParsingError(f"En-tête syslog Cisco FTD non reconnu : {line[:120]!r}")

    header_timestamp, firewall_device_ip, msg_id, body = match.groups()
    fields = _split_key_values(body)

    extra = {key: value for key, value in fields.items() if key not in _STRUCTURED_KEYS}
    extra["_syslog_header_timestamp"] = header_timestamp
    extra["_msg_id"] = msg_id

    parsed: dict = {
        "raw_line": line,
        "firewall_device_ip": firewall_device_ip,
        "first_packet_at": _parse_timestamp(fields.get("FirstPacketSecond")),
        "extra": extra,
    }
    for log_key, model_key in _STRING_FIELDS.items():
        parsed[model_key] = fields.get(log_key)
    for log_key, model_key in _INT_FIELDS.items():
        parsed[model_key] = _parse_int(fields.get(log_key))

    return parsed


def _split_key_values(body: str) -> dict:
    fields = {}
    for chunk in body.split(", "):
        if ": " not in chunk:
            continue
        key, value = chunk.split(": ", 1)
        fields[key] = value
    return fields


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")  # naïf, UTC implicite (voir docstring)

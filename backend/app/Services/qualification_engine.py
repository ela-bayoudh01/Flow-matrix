"""Qualification Engine : scoring par règles explicites (zone, port sensible, fréquence,
action connue) -> criticité + statut de sécurité par Flow. Pas de Machine Learning.

Toute la configuration (poids, seuils, listes) est regroupée ici, en haut du fichier --
jamais dispersée dans la logique -- pour rester ajustable après un premier passage sur
les données réelles. Voir docs/07-qualification-engine.md pour la justification complète
de chaque valeur, notamment la classification des zones (ZONE_ROLES), prouvée sur données
réelles (NAT, type d'IP destination, URLCategory, règles ACL associées) et non supposée.
"""

import collections
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Flow

# --- Zone : rôle interne/externe de chaque zone réelle (cf. docs/07, classification prouvée) ---
ZONE_ROLES: dict[str, str] = {
    "Internet_Zone": "externe",
    "ADSL_Zone": "externe",
    "Users_Zone": "interne",
    "ATD_Users_Zone": "interne",
    "Call_Center_Zone": "interne",
    "Servers_Zone": "interne",
    "Voice_Zone": "interne",
    "ESCALE_DCS_ZONE": "interne",
    "SABENA_Zone": "interne",
    "WAN_Zone": "interne",
    "Interco_Zone": "interne",
}
UNCLASSIFIED_ROLE = "inconnue"

ZONE_DIRECTION_POINTS: dict[tuple[str, str], int] = {
    ("externe", "interne"): 40,
    ("interne", "interne"): 10,
    ("interne", "externe"): 5,
    ("externe", "externe"): 20,  # jamais observé sur les données réelles, prudence par défaut
}
ZONE_UNCLASSIFIED_POINTS = 15

# --- Port : services sensibles (Telnet, FTP, SMB, RDP, SNMP -- à valider/compléter) ---
SENSITIVE_PORTS: set[int] = {23, 21, 139, 445, 3389, 161}
COMMON_SAFE_PORTS: set[int] = {443, 80, 53}
PORT_SENSITIVE_POINTS = 30
PORT_SAFE_POINTS = 0
PORT_UNKNOWN_POINTS = 10

# --- Fréquence : occurrence_count du Flow -- CONDITIONNELLE (itération 2, 2026-08-12) : ne
# compte que si zone ou port montre déjà un signal au-dessus de son niveau le plus bénin.
# Motif : sur les 31 421 flows réels, la fréquence seule faisait basculer 81% de TOUT le
# trafic en "medium" (deux pics nets à 23 et 30 sur 11 valeurs de score possibles), noyant
# le signal utile sous du bruit de navigation web normale. Voir docs/07-qualification-engine.md,
# section "Itération 2" pour la comparaison chiffrée avant/après.
FREQUENCY_RARE_MAX = 1
FREQUENCY_MODERATE_MAX = 5
FREQUENCY_RARE_POINTS = 15
FREQUENCY_MODERATE_POINTS = 8
FREQUENCY_COMMON_POINTS = 0
# Signal minimal : zone/port au-delà de leur catégorie la plus bénigne déclenchent la prise en
# compte de la fréquence. Côté zone, les catégories bénignes sont "interne_vers_externe" (trafic
# normal) *et* "zone_non_classifiee" (absence d'info, pas un risque avéré -- cf. qualify()).
# Côté port, seul "port_courant" (443/80/53) est bénin.
PORT_BASELINE_POINTS = PORT_SAFE_POINTS

# --- Action : dominant_action du Flow ---
ACTION_POINTS: dict[str, int] = {"Allow": 10, "Block": 0, "Mixed": 15}

# --- Seuils de criticité (du plus haut au plus bas) ---
CRITICALITY_THRESHOLDS: list[tuple[int, str]] = [
    (65, "critical"),
    (40, "high"),
    (20, "medium"),
    (0, "low"),
]


def qualify(flow: Flow) -> dict:
    """Calcule la qualification d'un Flow. Fonction pure : ne modifie pas flow, ne touche
    pas la base. L'appelant décide d'appliquer le résultat (voir qualify_all)."""
    zone_points, zone_reason = _score_zone(flow.ingress_zone, flow.egress_zone)
    port_points, port_reason = _score_port(flow.dst_port)
    # "zone_non_classifiee" (15 pts, catégorie ci-dessus le seuil "interne_vers_externe" à 5)
    # est une absence d'information, pas un signal élevé -- ne doit donc jamais déclencher la
    # fréquence à elle seule. Sans cette exclusion, toute zone absente de ZONE_ROLES fait
    # automatiquement passer du trafic banal (Allow/port courant/1 occurrence) en "high" (bug
    # réel trouvé sur TUN-ARP-BOX-FWBJ, 2207/2299 flux "high" concernés -- docs/07).
    zone_is_signal = zone_reason["category"] not in ("interne_vers_externe", "zone_non_classifiee")
    port_is_signal = port_points > PORT_BASELINE_POINTS
    signal_present = zone_is_signal or port_is_signal
    frequency_points, frequency_reason = _score_frequency(flow.occurrence_count, signal_present)
    action_points, action_reason = _score_action(flow.dominant_action)

    total_score = zone_points + port_points + frequency_points + action_points
    label = _label_for_score(total_score)

    return {
        "criticality_score": float(total_score),
        "criticality_label": label,
        "security_status": _security_status(flow.validation_status, label),
        "qualification_reasons": {
            "zone": zone_reason,
            "port": port_reason,
            "frequency": frequency_reason,
            "action": action_reason,
            "total_score": total_score,
            "label": label,
        },
    }


def qualify_all(session: Session, source: Optional[str] = None) -> dict:
    """Qualifie tous les Flow (ou ceux d'une source donnée), écrit le résultat, commit.
    Retourne un résumé (nombre qualifié, répartition par label, zones absentes de ZONE_ROLES
    rencontrées) pour vérification.
    """
    query = session.query(Flow)
    if source is not None:
        query = query.filter(Flow.source == source)

    label_counts: collections.Counter = collections.Counter()
    unclassified_zones: set[str] = set()
    total = 0
    for flow in query.all():
        result = qualify(flow)
        flow.criticality_score = result["criticality_score"]
        flow.criticality_label = result["criticality_label"]
        flow.security_status = result["security_status"]
        flow.qualification_reasons = result["qualification_reasons"]
        label_counts[result["criticality_label"]] += 1
        total += 1
        for zone in (flow.ingress_zone, flow.egress_zone):
            if zone and zone not in ZONE_ROLES:
                unclassified_zones.add(zone)
    session.commit()

    return {
        "total_qualified": total,
        "label_counts": dict(label_counts),
        "unclassified_zones": sorted(unclassified_zones),
    }


def _score_zone(ingress_zone: Optional[str], egress_zone: Optional[str]) -> tuple[int, dict]:
    ingress_role = ZONE_ROLES.get(ingress_zone, UNCLASSIFIED_ROLE) if ingress_zone else UNCLASSIFIED_ROLE
    egress_role = ZONE_ROLES.get(egress_zone, UNCLASSIFIED_ROLE) if egress_zone else UNCLASSIFIED_ROLE

    if UNCLASSIFIED_ROLE in (ingress_role, egress_role):
        points = ZONE_UNCLASSIFIED_POINTS
        category = "zone_non_classifiee"
    else:
        points = ZONE_DIRECTION_POINTS.get((ingress_role, egress_role), ZONE_UNCLASSIFIED_POINTS)
        category = f"{ingress_role}_vers_{egress_role}"

    return points, {
        "ingress_zone": ingress_zone,
        "egress_zone": egress_zone,
        "category": category,
        "points": points,
    }


def _score_port(dst_port: Optional[int]) -> tuple[int, dict]:
    if dst_port in SENSITIVE_PORTS:
        points, category = PORT_SENSITIVE_POINTS, "port_sensible"
    elif dst_port in COMMON_SAFE_PORTS:
        points, category = PORT_SAFE_POINTS, "port_courant"
    else:
        points, category = PORT_UNKNOWN_POINTS, "port_non_classifie"
    return points, {"value": dst_port, "category": category, "points": points}


def _score_frequency(occurrence_count: Optional[int], signal_present: bool) -> tuple[int, dict]:
    count = occurrence_count or 0

    if not signal_present:
        return 0, {
            "occurrence_count": count,
            "category": "ignoree_sans_signal_zone_ou_port",
            "points": 0,
            "signal_present": False,
        }

    if count <= FREQUENCY_RARE_MAX:
        points, category = FREQUENCY_RARE_POINTS, "rare"
    elif count <= FREQUENCY_MODERATE_MAX:
        points, category = FREQUENCY_MODERATE_POINTS, "modere"
    else:
        points, category = FREQUENCY_COMMON_POINTS, "frequent"
    return points, {
        "occurrence_count": count,
        "category": category,
        "points": points,
        "signal_present": True,
    }


def _score_action(dominant_action: Optional[str]) -> tuple[int, dict]:
    points = ACTION_POINTS.get(dominant_action, 0)
    return points, {"value": dominant_action, "points": points}


def _label_for_score(score: int) -> str:
    for threshold, label in CRITICALITY_THRESHOLDS:
        if score >= threshold:
            return label
    return CRITICALITY_THRESHOLDS[-1][1]


def _security_status(validation_status: Optional[str], criticality_label: str) -> str:
    if validation_status == "approved":
        return "legitimate"
    if validation_status == "blocked":
        return "at_risk"
    return "at_risk" if criticality_label in ("high", "critical") else "unknown"

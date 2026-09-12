"""Sous-réseaux observés à partir des IP source des Flow (2026-09-10, demande de l'encadrant)
-- FONCTIONNALITÉ NOUVELLE et VOLONTAIREMENT ISOLÉE : aucun lien avec Flow.decided_action, le
diff de cycle (Services/validation_cycle_engine.py), ou FlowSnapshot -- lit uniquement les Flow
pour compter, ne les modifie jamais.

Regroupement PUREMENT SUGGESTIF, jamais une vérité : le système ne peut pas connaître le vrai
découpage réseau de Nouvelair à partir des seules IP observées dans les logs -- juste un point
de départ, affinable via `prefix_length` (l'encadrant seul juge de la granularité pertinente
selon ce qu'il sait réellement de la structure du réseau). Toujours affiché avec cette réserve
côté interface (cf. NetworkPoliciesPage.tsx).
"""

import ipaddress
from collections import defaultdict
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Flow

MIN_PREFIX_LENGTH = 1
MAX_PREFIX_LENGTH = 32
DEFAULT_PREFIX_LENGTH = 24


def cidr_for_ip(ip_str: str, prefix_length: int) -> Optional[str]:
    """Réseau CIDR (chaîne, ex. "10.67.1.0/24") contenant `ip_str` pour ce `prefix_length`,
    ou None si `ip_str` est invalide/vide/IPv6 -- IPv6 exclu du regroupement (le sélecteur
    /16.../30 n'a de sens qu'en IPv4), jamais une exception pour autant, juste absent du
    résultat côté appelant. Seule définition du regroupement IP -> CIDR du projet -- réutilisée
    par `observed_subnets` ci-dessous ET par
    Services/validation_cycle_engine.py::compute_subnet_diff (2026-09-11, demande de
    l'encadrant : même regroupement suggestif, appliqué cette fois aux écarts de cycle plutôt
    qu'au simple comptage de Flow) -- jamais une deuxième implémentation susceptible de
    diverger.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.version != 4:
            return None
        return str(ipaddress.ip_network(f"{ip_str}/{prefix_length}", strict=False))
    except ValueError:
        return None


def observed_subnets(session: Session, *, source: str, prefix_length: int = DEFAULT_PREFIX_LENGTH) -> list[dict]:
    """Pour `source`, regroupe les IP source des Flow par préfixe CIDR de longueur
    `prefix_length` -- {"cidr", "machine_count" (IP distinctes dans ce préfixe), "flow_count"
    (nombre de Flow -- pas d'occurrences brutes, cf. vocabulaire "flux" du reste du projet)}.
    Une IP invalide/vide/IPv6 est silencieusement exclue (cf. cidr_for_ip) plutôt que de faire
    échouer tout le calcul pour les autres.
    """
    if not (MIN_PREFIX_LENGTH <= prefix_length <= MAX_PREFIX_LENGTH):
        raise ValueError(f"prefix_length doit être entre {MIN_PREFIX_LENGTH} et {MAX_PREFIX_LENGTH}")

    rows = (
        session.query(Flow.src_ip, func.count(Flow.id))
        .filter(Flow.source == source)
        .group_by(Flow.src_ip)
        .all()
    )

    buckets: dict[str, dict] = defaultdict(lambda: {"machines": set(), "flow_count": 0, "network": None})
    for src_ip, flow_count in rows:
        cidr = cidr_for_ip(src_ip, prefix_length)
        if cidr is None:
            continue
        bucket = buckets[cidr]
        bucket["machines"].add(src_ip)
        bucket["flow_count"] += flow_count
        bucket["network"] = ipaddress.ip_network(cidr)

    result = [
        {"cidr": cidr, "machine_count": len(bucket["machines"]), "flow_count": bucket["flow_count"]}
        for cidr, bucket in buckets.items()
    ]
    result.sort(key=lambda r: buckets[r["cidr"]]["network"])
    return result

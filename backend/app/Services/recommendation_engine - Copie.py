"""Recommendation Engine : détecte, sur le trafic RÉELLEMENT observé, des indices de règles
ACL déjà appliquées par le firewall qui semblent trop permissives, obsolètes (par usage), ou
des segments de trafic sans règle explicite (gouvernés uniquement par l'action par défaut).

Ne compare jamais à un export de config FMC (`show access-list`) : cette source n'a jamais
été fournie (docs/00 §4). Limite assumée et explicitée dans chaque finding : on détecte "pas
vu récemment / diversité large / pas de règle nommée dans les logs", pas "n'existe plus / mal
configuré sur le firewall" au sens absolu.

Jamais de proposition de nouvelle règle ici (rôle futur de l'ACL Engine, pas commencé) --
uniquement un diagnostic explicable (`evidence`, jamais un score seul opaque, même principe
que qualification_engine.qualify), soumis à revue humaine (`RuleRecommendation.status`).

Seuils calibrés sur `flow_matrix.db` réel le 2026-08-13 (voir docs/09-recommendation-engine.md
pour la mesure complète) -- pas devinés à l'avance. Important : un résultat "aucun finding
trop_permissive détecté" est un constat sur les données actuelles (peu de règles nommées,
fenêtre d'observation courte), pas une preuve que la logique ne peut jamais rien trouver --
les seuils sont génériques et réévalués à chaque exécution, cf. docs/09.
"""

import collections
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Flow, RuleRecommendation, ZONE_UNSET
from .qualification_engine import SENSITIVE_PORTS

DEFAULT_ACTION_RULE_NAME = "Default Action"

FINDING_TROP_PERMISSIVE = "trop_permissive"
FINDING_OBSOLETE = "obsolete"
FINDING_SANS_REGLE_EXPLICITE = "sans_regle_explicite"

HIGH_CRITICALITY_LABELS = {"high", "critical"}

# --- Trop permissive : diversité de dst_port au-delà de ce seuil, OU présence d'au moins un
# flow high/critical sous la règle, OU port sensible observé -- pas de seuil sur dst_ip
# (mesure réelle : la diversité de dst_ip vient de la navigation web légitime, signal
# trompeur, même piège que la fréquence en itération 2 du Qualification Engine). ---
PERMISSIVE_DISTINCT_DST_PORT_THRESHOLD = 10

# --- Obsolète : désactivée tant que la fenêtre d'observation totale du jeu de données est
# trop courte pour qu'"inactif depuis N jours" ait un sens (mesure réelle : ~4,5 jours de
# logs -> toutes les règles à moins de 0,5 jour d'écart, non discriminant). ---
MIN_OBSERVATION_WINDOW_DAYS = 14
OBSOLETE_INACTIVITY_DAYS = 30


def run(session: Session, source: Optional[str] = None) -> dict:
    """Exécute le moteur sur les Flow existants (filtrés par `source` si fourni), upsert les
    findings détectés dans RuleRecommendation, commit. Idempotent : ré-exécutable après
    chaque import sans dupliquer les lignes ni écraser une revue humaine déjà faite.
    Retourne un résumé (comptes par type, fenêtre d'observation, statut de la garde obsolète).
    """
    query = session.query(Flow)
    if source is not None:
        query = query.filter(Flow.source == source)
    flows = query.all()

    dataset_min, dataset_max = _observation_window(flows)
    window_days = (dataset_max - dataset_min).total_seconds() / 86400 if dataset_min and dataset_max else None
    obsolete_enabled = window_days is not None and window_days >= MIN_OBSERVATION_WINDOW_DAYS

    named_groups: dict[tuple, list[Flow]] = collections.defaultdict(list)
    default_action_groups: dict[tuple, list[Flow]] = collections.defaultdict(list)

    for flow in flows:
        rule_name = flow.last_access_control_rule_name
        if not rule_name:
            # Pas de nom de règle dans le log source pour ce Flow : ne peut être attribué à
            # aucune règle ni au segment "Default Action" -- exclu de l'analyse (limite
            # connue, cf. docs/09-recommendation-engine.md), jamais deviné.
            continue
        if rule_name == DEFAULT_ACTION_RULE_NAME:
            key = (flow.source, flow.ingress_zone or ZONE_UNSET, flow.egress_zone or ZONE_UNSET)
            default_action_groups[key].append(flow)
        else:
            named_groups[(flow.source, rule_name)].append(flow)

    findings: list[dict] = []
    for (src, rule_name), group_flows in named_groups.items():
        findings.extend(_evaluate_named_rule(src, rule_name, group_flows, dataset_max, obsolete_enabled))
    for (src, ingress_zone, egress_zone), group_flows in default_action_groups.items():
        findings.append(_evaluate_default_action(src, ingress_zone, egress_zone, group_flows))

    summary = _upsert_findings(session, findings)
    summary["observation_window_days"] = round(window_days, 2) if window_days is not None else None
    summary["obsolete_detection_enabled"] = obsolete_enabled
    return summary


def _observation_window(flows: list[Flow]) -> tuple[Optional[datetime], Optional[datetime]]:
    starts = [f.first_seen_at for f in flows if f.first_seen_at is not None]
    ends = [f.last_seen_at for f in flows if f.last_seen_at is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def _evaluate_named_rule(
    source: Optional[str],
    rule_name: str,
    group_flows: list[Flow],
    dataset_max: Optional[datetime],
    obsolete_enabled: bool,
) -> list[dict]:
    findings = []

    distinct_dst_ip = {f.dst_ip for f in group_flows}
    distinct_dst_port = {f.dst_port for f in group_flows}
    distinct_protocol = {f.protocol for f in group_flows}
    distinct_src_ip = {f.src_ip for f in group_flows}
    distinct_zone_pairs = {(f.ingress_zone, f.egress_zone) for f in group_flows}
    sensitive_ports_observed = sorted(distinct_dst_port & SENSITIVE_PORTS)
    high_or_critical = [f for f in group_flows if f.criticality_label in HIGH_CRITICALITY_LABELS]
    criticality_breakdown = collections.Counter(f.criticality_label or "non_qualifie" for f in group_flows)

    port_over_threshold = len(distinct_dst_port) > PERMISSIVE_DISTINCT_DST_PORT_THRESHOLD
    high_or_critical_present = len(high_or_critical) > 0
    sensitive_port_present = len(sensitive_ports_observed) > 0

    if port_over_threshold or high_or_critical_present or sensitive_port_present:
        findings.append(
            {
                "source": source,
                "finding_type": FINDING_TROP_PERMISSIVE,
                "rule_name": rule_name,
                "flow_count": len(group_flows),
                "evidence": {
                    "distinct_dst_ip": len(distinct_dst_ip),
                    "distinct_dst_port": len(distinct_dst_port),
                    "distinct_protocol": len(distinct_protocol),
                    "distinct_src_ip": len(distinct_src_ip),
                    "distinct_zone_pairs": len(distinct_zone_pairs),
                    "sensitive_ports_observed": sensitive_ports_observed,
                    "high_or_critical_flow_count": len(high_or_critical),
                    "criticality_breakdown": dict(criticality_breakdown),
                    "triggers": {
                        "distinct_dst_port_over_threshold": port_over_threshold,
                        "high_or_critical_present": high_or_critical_present,
                        "sensitive_port_present": sensitive_port_present,
                    },
                    "thresholds": {"distinct_dst_port_threshold": PERMISSIVE_DISTINCT_DST_PORT_THRESHOLD},
                },
            }
        )

    if obsolete_enabled:
        rule_last_seen = max((f.last_seen_at for f in group_flows if f.last_seen_at is not None), default=None)
        if rule_last_seen is not None and dataset_max is not None:
            inactivity_days = (dataset_max - rule_last_seen).total_seconds() / 86400
            if inactivity_days > OBSOLETE_INACTIVITY_DAYS:
                findings.append(
                    {
                        "source": source,
                        "finding_type": FINDING_OBSOLETE,
                        "rule_name": rule_name,
                        "flow_count": len(group_flows),
                        "evidence": {
                            "rule_last_seen_at": rule_last_seen.isoformat(),
                            "dataset_reference_at": dataset_max.isoformat(),
                            "inactivity_days": round(inactivity_days, 2),
                            "threshold_days": OBSOLETE_INACTIVITY_DAYS,
                        },
                    }
                )

    return findings


def _evaluate_default_action(
    source: Optional[str], ingress_zone: str, egress_zone: str, group_flows: list[Flow]
) -> dict:
    allow_count = sum(f.allow_count for f in group_flows)
    block_count = sum(f.block_count for f in group_flows)
    high_or_critical = [f for f in group_flows if f.criticality_label in HIGH_CRITICALITY_LABELS]

    if allow_count > 0:
        note = (
            "Au moins une connexion autorisée sans règle explicite sous ce couple de zones -- "
            "à traiter en priorité, contrairement à un segment purement bloqué par défaut."
        )
    else:
        note = (
            "Comportement par défaut du firewall (deny) observé à 100% ici : pas de risque actif "
            "constaté aujourd'hui, mais aucune politique explicite n'a été formalisée pour ce "
            "couple de zones -- gouvernance à clarifier, pas nécessairement une urgence sécurité."
        )

    return {
        "source": source,
        "finding_type": FINDING_SANS_REGLE_EXPLICITE,
        "rule_name": DEFAULT_ACTION_RULE_NAME,
        "ingress_zone": ingress_zone,
        "egress_zone": egress_zone,
        "flow_count": len(group_flows),
        "evidence": {
            "allow_count": allow_count,
            "block_count": block_count,
            "high_or_critical_flow_count": len(high_or_critical),
            "note": note,
        },
    }


def _upsert_findings(session: Session, findings: list[dict]) -> dict:
    """Crée les nouveaux findings, met à jour l'evidence de ceux qui existent déjà -- sans
    jamais toucher `status`/`reviewed_by`/`reviewed_at` d'un finding déjà revu par un humain.
    Ne supprime ni ne referme automatiquement les findings qui ne sont plus détectés à ce
    passage (limite connue, cf. docs/09-recommendation-engine.md, "évolution future").
    """
    type_counts: collections.Counter = collections.Counter()
    created, updated = 0, 0

    for finding in findings:
        type_counts[finding["finding_type"]] += 1
        identity_filter = {
            "source": finding["source"],
            "finding_type": finding["finding_type"],
            "rule_name": finding["rule_name"],
            "ingress_zone": finding.get("ingress_zone", ZONE_UNSET),
            "egress_zone": finding.get("egress_zone", ZONE_UNSET),
        }
        existing = (
            session.query(RuleRecommendation)
            .filter_by(**identity_filter)
            .one_or_none()
        )
        if existing is None:
            session.add(RuleRecommendation(flow_count=finding["flow_count"], evidence=finding["evidence"], **identity_filter))
            created += 1
        else:
            existing.flow_count = finding["flow_count"]
            existing.evidence = finding["evidence"]
            updated += 1

    session.commit()
    return {
        "total_findings": len(findings),
        "findings_by_type": dict(type_counts),
        "created": created,
        "updated": updated,
    }

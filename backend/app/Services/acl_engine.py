"""ACL Engine : génère des propositions de règles ACL (`AclProposal`), jamais appliquées
automatiquement au firewall -- toujours soumises à validation humaine avant intégration
manuelle dans FMC. Trois intents générés automatiquement, chacun déclenché par une décision
humaine déjà prise ailleurs dans l'outil (jamais une génération spéculative à partir d'un
simple constat), plus un quatrième ajouté directement à la main :

- "create"  : un Flow approuvé (`validation_status="approved"`) encore couvert uniquement
              par "Default Action" -- formalise en règle explicite un accès jusque-là géré
              par le comportement par défaut du firewall.
- "tighten" : une RuleRecommendation "trop_permissive" acquittée -- propose de resserrer la
              règle existante ciblée (`target_rule_name`).
- "revoke"  : une RuleRecommendation "obsolete" acquittée -- propose de retirer la règle
              existante ciblée.
- "manual"  : construite par `build_manual_proposal()` à la demande du Responsable Réseau,
              pour un flux/équipement pas encore observé dans les logs -- pas générée par
              `run()`, ajoutée directement via `POST /api/acl-proposals`.

Fiche structurée (zone/objet réseau/port/protocole/action) dans `proposed_rule_text`, jamais
une ligne au format `access-list` ASA -- clarifié le 2026-08-13 (docs/01-journal-technique.md) :
un FTD géré par FMC n'accepte pas cette syntaxe pour ses règles de trafic, seule une fiche
structurée, ressaisie manuellement dans FMC, est utilisable.
"""

import collections
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import AclProposal, Flow, RuleRecommendation, ValidationCycle, RULE_NAME_UNSET, ZONE_UNSET
from . import validation_cycle_engine
from .recommendation_engine import DEFAULT_ACTION_RULE_NAME

# Au-delà de ce nombre d'hôtes distincts, on n'énumère plus (même principe que
# dimension_notice/LARGE_RESULT_CELL_THRESHOLD -- jamais un résultat trompeur silencieux).
NETWORK_ENUMERATION_CAP = 50


def run(session: Session, source: Optional[str] = None, since: Optional[datetime] = None) -> dict:
    """Exécute les 3 générateurs, upsert les propositions, commit. Idempotent : ré-exécutable
    sans dupliquer ni écraser une revue humaine déjà faite (même pattern que
    Services/recommendation_engine.py, éprouvé et réutilisé tel quel).

    `since` (optionnel) restreint aux flux approuvés / findings acquittés **depuis** cette
    date -- utilisé par `run_for_cycle()` pour ne considérer que ce qui vient d'être validé
    dans le cycle courant, jamais tout l'historique. `since=None` (comportement par défaut,
    utilisé par le déclenchement manuel `POST /api/acl-proposals/run` sans cycle) garde le
    comportement d'origine : tout l'historique approuvé/acquitté, sans fenêtre de temps.
    """
    create_findings, create_detail = _generate_create(session, source, since)
    tighten_findings = _generate_tighten(session, source, since)
    revoke_findings = _generate_revoke(session, source, since)

    # merge=True (since is not None) : ce `run()` ne voit qu'une tranche partielle des flux
    # approuvés (depuis le cycle précédent), jamais la vérité complète -- fusionner avec
    # l'existant plutôt que remplacer, sinon un flux approuvé lors d'un cycle antérieur
    # disparaîtrait de la proposition à chaque nouveau cycle. merge=False (rescan complet,
    # since=None) garde le comportement d'origine : remplacer, pour bien retirer un flux qui
    # ne correspond plus (ex. re-bloqué depuis), ce qu'une fusion ne ferait jamais.
    summary = _upsert_proposals(session, create_findings + tighten_findings + revoke_findings, merge=since is not None)
    summary["by_intent"] = {
        "create": len(create_findings),
        "tighten": len(tighten_findings),
        "revoke": len(revoke_findings),
    }
    summary["create_detail"] = create_detail
    return summary


def run_for_cycle(session: Session, cycle: ValidationCycle) -> dict:
    """Génère les propositions ACL pour la source d'un ValidationCycle qui vient d'être
    clôturé, à la demande explicite de l'encadrant (2026-08-21) : l'ACL Engine ne doit plus
    être une action indépendante permanente, mais une étape du cycle -- déclenchée
    manuellement juste après la clôture (jamais automatique), scopée aux flux
    approuvés/acquittés depuis le cycle précédent de CETTE source.

    Fenêtre : `since = previous_cycle.closed_at` (le cycle qu'on vient de remplacer), ou
    `None` s'il s'agit du tout premier cycle de cette source (alors équivalent à l'ancien
    comportement global, mais déjà borné à cette seule source). Choix délibéré vs. limiter
    strictement aux flux "nouveau"/"modifie" du diff de ce cycle : un flux resté "pending"
    plus longtemps que son propre cycle (approuvé en retard, après coup, depuis la Table des
    flux) ne serait alors plus jamais repris par aucun cycle suivant ("strandé") -- borner sur
    `validated_at`/`reviewed_at` couvre aussi ce cas, sans jamais oublier un flux approuvé.
    """
    previous = validation_cycle_engine.previous_cycle_for(session, cycle)
    since = previous.closed_at if previous else None
    return run(session, source=cycle.source, since=since)


# --- "create" : Flow approuvé encore sous Default Action -----------------------------------


def _generate_create(session: Session, source: Optional[str], since: Optional[datetime] = None) -> tuple[list[dict], dict]:
    """Retourne (findings, detail). `detail` existe pour que "0 proposition" ne ressemble
    jamais à un échec silencieux (cas réel rencontré : 4 flux approuvés, 0 proposition, aucun
    moyen de savoir sans creuser la base à la main que les 4 étaient déjà couverts par une
    règle nommée -- rien à créer, pas un bug) : `considered` = tous les flux approuvés dans le
    périmètre (source + fenêtre `since`), `already_covered` = ceux déjà régis par une règle
    explicite (pas de proposition "create" possible), `eligible` = ceux réellement sous
    Default Action (`considered - already_covered`, ce qui alimente les findings ci-dessous).
    """
    query = session.query(Flow).filter(Flow.validation_status == "approved")
    if source is not None:
        query = query.filter(Flow.source == source)
    if since is not None:
        query = query.filter(Flow.validated_at > since)

    approved_flows = query.all()
    eligible_flows = [f for f in approved_flows if f.last_access_control_rule_name == DEFAULT_ACTION_RULE_NAME]
    detail = {
        "considered": len(approved_flows),
        "eligible": len(eligible_flows),
        "already_covered": len(approved_flows) - len(eligible_flows),
    }

    groups: dict[tuple, list[Flow]] = collections.defaultdict(list)
    for flow in eligible_flows:
        key = (flow.source, flow.ingress_zone or ZONE_UNSET, flow.egress_zone or ZONE_UNSET, flow.protocol, flow.dst_port)
        groups[key].append(flow)

    findings = [
        _build_create_proposal(session, src, izone, ezone, protocol, port, flows)
        for (src, izone, ezone, protocol, port), flows in groups.items()
    ]
    return findings, detail


def _build_create_proposal(
    session: Session, source: Optional[str], ingress_zone: str, egress_zone: str,
    protocol: Optional[str], dst_port: Optional[int], flows: list[Flow],
) -> dict:
    src_networks = network_summary(sorted({f.src_ip for f in flows}))
    dst_networks = network_summary(sorted({f.dst_ip for f in flows}))

    # Rapprochement best-effort avec le finding "sans_regle_explicite" correspondant (même
    # regroupement -- source/zones), pour la traçabilité. Jamais un lien obligatoire : un Flow
    # peut être approuvé sans qu'un finding ait été généré (ex. avant la première exécution
    # du Recommendation Engine).
    recommendation = (
        session.query(RuleRecommendation)
        .filter_by(source=source, finding_type="sans_regle_explicite", ingress_zone=ingress_zone, egress_zone=egress_zone)
        .one_or_none()
    )

    suggested_name = (
        f"CREATE_{slug(ingress_zone)}_TO_{slug(egress_zone)}_{(protocol or 'ANY').upper()}_{dst_port if dst_port is not None else 'ANY'}"
    )
    rationale = {
        "trigger": "flow_approved_under_default_action",
        "flow_ids": [f.id for f in flows],
        "source_recommendation_id": recommendation.id if recommendation else None,
        "distinct_src_ip": src_networks["count"],
        "distinct_dst_ip": dst_networks["count"],
    }
    rule_text = _format_create_rule_text(suggested_name, ingress_zone, egress_zone, protocol, dst_port, src_networks, dst_networks, flows)

    return {
        "source": source, "intent": "create",
        "ingress_zone": ingress_zone, "egress_zone": egress_zone,
        "protocol": protocol, "dst_port": dst_port, "target_rule_name": RULE_NAME_UNSET,
        "proposed_action": "Allow", "suggested_rule_name": suggested_name,
        "src_networks": src_networks, "dst_networks": dst_networks,
        "source_recommendation_id": recommendation.id if recommendation else None,
        "rationale": rationale, "proposed_rule_text": rule_text, "flows": flows,
    }


def _format_create_rule_text(name, ingress_zone, egress_zone, protocol, dst_port, src_networks, dst_networks, flows) -> str:
    validators = sorted({f.validated_by for f in flows if f.validated_by}) or ["(non renseigné)"]
    return (
        f"Nom suggéré         : {name}\n"
        f"Zone source          : {ingress_zone}\n"
        f"Zone destination      : {egress_zone}\n"
        f"Réseaux source         : {format_network_desc(src_networks)}\n"
        f"Réseaux destination     : {format_network_desc(dst_networks)}\n"
        f"Protocole/Port            : {(protocol or 'any').upper()}/{dst_port if dst_port is not None else 'any'}\n"
        f"Action proposée             : Allow\n"
        f"Justification                 : {len(flows)} flux validé(s) par {', '.join(validators)}, jusqu'ici "
        "couvert(s) uniquement par Default Action (aucune règle explicite)."
    )


# --- "tighten" : RuleRecommendation trop_permissive acquittée ------------------------------


def _generate_tighten(session: Session, source: Optional[str], since: Optional[datetime] = None) -> list[dict]:
    query = session.query(RuleRecommendation).filter(
        RuleRecommendation.finding_type == "trop_permissive", RuleRecommendation.status == "acknowledged"
    )
    if source is not None:
        query = query.filter(RuleRecommendation.source == source)
    if since is not None:
        query = query.filter(RuleRecommendation.reviewed_at > since)
    return [_build_rule_targeted_proposal(r, intent="tighten", proposed_action="Allow") for r in query.all()]


# --- "revoke" : RuleRecommendation obsolete acquittée ---------------------------------------


def _generate_revoke(session: Session, source: Optional[str], since: Optional[datetime] = None) -> list[dict]:
    query = session.query(RuleRecommendation).filter(
        RuleRecommendation.finding_type == "obsolete", RuleRecommendation.status == "acknowledged"
    )
    if source is not None:
        query = query.filter(RuleRecommendation.source == source)
    if since is not None:
        query = query.filter(RuleRecommendation.reviewed_at > since)
    return [_build_rule_targeted_proposal(r, intent="revoke", proposed_action="Remove") for r in query.all()]


def _build_rule_targeted_proposal(recommendation: RuleRecommendation, *, intent: str, proposed_action: str) -> dict:
    prefix = intent.upper()
    suggested_name = f"{prefix}_{recommendation.rule_name}"
    triggers = (recommendation.evidence or {}).get("triggers", {})
    reasons = [k for k, v in triggers.items() if v] or ["voir evidence du finding"]

    action_text = "resserrer la portée (moindre privilège)" if intent == "tighten" else "retirer cette règle"
    rule_text = (
        f"Nom suggéré  : {suggested_name}\n"
        f"Règle ciblée  : {recommendation.rule_name} (source {recommendation.source})\n"
        f"Action proposée : {action_text}\n"
        f"Justification   : finding #{recommendation.id} ({recommendation.finding_type}) acquitté -- {', '.join(reasons)}. "
        "À vérifier et appliquer manuellement dans FMC, cette proposition ne modifie rien automatiquement."
    )
    rationale = {
        "trigger": "recommendation_acknowledged",
        "source_recommendation_id": recommendation.id,
        "evidence": recommendation.evidence,
    }

    return {
        "source": recommendation.source, "intent": intent,
        "ingress_zone": ZONE_UNSET, "egress_zone": ZONE_UNSET,
        "protocol": None, "dst_port": None, "target_rule_name": recommendation.rule_name,
        "proposed_action": proposed_action, "suggested_rule_name": suggested_name,
        "src_networks": None, "dst_networks": None,
        "source_recommendation_id": recommendation.id,
        "rationale": rationale, "proposed_rule_text": rule_text, "flows": [],
    }


# --- "manual" : ajoutée directement par le Responsable Réseau ------------------------------


def build_manual_proposal(
    *, source: Optional[str], ingress_zone: Optional[str], egress_zone: Optional[str],
    protocol: Optional[str], dst_port: Optional[int], src_ips: list[str], dst_ips: list[str],
    proposed_action: str, suggested_rule_name: Optional[str], target_rule_name: Optional[str],
    justification: str, created_by: Optional[str],
) -> AclProposal:
    """Construit (sans committer -- à la charge de l'appelant) une AclProposal "manual" pour
    un flux/équipement pas encore observé dans les logs -- il n'y a donc aucun Flow ni
    RuleRecommendation à rattacher, contrairement aux trois intents générés par `run()`.
    `justification` est obligatoire : contrairement aux propositions générées (evidence/
    rationale calculés), une entrée manuelle n'a de preuve que celle que l'humain fournit.
    """
    ingress_zone = ingress_zone or ZONE_UNSET
    egress_zone = egress_zone or ZONE_UNSET
    target_rule_name = target_rule_name or RULE_NAME_UNSET
    src_networks = network_summary(sorted(src_ips))
    dst_networks = network_summary(sorted(dst_ips))
    suggested_name = suggested_rule_name or (
        f"MANUAL_{slug(ingress_zone)}_TO_{slug(egress_zone)}_{(protocol or 'ANY').upper()}_{dst_port if dst_port is not None else 'ANY'}"
    )
    rule_text = (
        f"Nom suggéré         : {suggested_name}\n"
        f"Zone source          : {ingress_zone}\n"
        f"Zone destination      : {egress_zone}\n"
        f"Réseaux source         : {format_network_desc(src_networks)}\n"
        f"Réseaux destination     : {format_network_desc(dst_networks)}\n"
        f"Protocole/Port            : {(protocol or 'any').upper()}/{dst_port if dst_port is not None else 'any'}\n"
        f"Action proposée             : {proposed_action}\n"
        f"Justification (ajout manuel)  : {justification}"
    )
    return AclProposal(
        source=source, intent="manual",
        ingress_zone=ingress_zone, egress_zone=egress_zone,
        protocol=protocol, dst_port=dst_port,
        src_networks=src_networks, dst_networks=dst_networks,
        proposed_action=proposed_action, suggested_rule_name=suggested_name,
        target_rule_name=target_rule_name, source_recommendation_id=None,
        rationale={"trigger": "manual_entry", "note": justification, "created_by": created_by},
        proposed_rule_text=rule_text,
    )


# --- Utilitaires partagés -------------------------------------------------------------------


def network_summary(ips: list[str]) -> dict:
    if len(ips) <= NETWORK_ENUMERATION_CAP:
        return {"observed": ips, "count": len(ips), "truncated": False}
    return {"observed": ips[:10], "count": len(ips), "truncated": True}


def format_network_desc(summary: dict) -> str:
    if summary["count"] == 0:
        return "any"
    if summary["truncated"]:
        sample = ", ".join(summary["observed"][:5])
        return f"{summary['count']} hôtes observés (trop nombreux pour être énumérés, échantillon : {sample}...)"
    return f"{', '.join(summary['observed'])} ({summary['count']} hôte(s) observé(s))"


def slug(value: Optional[str]) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value or "ANY").strip("_") or "ANY"


def _upsert_proposals(session: Session, findings: list[dict], merge: bool = False) -> dict:
    """Même logique que Services/recommendation_engine.py::_upsert_findings : crée les
    nouvelles propositions, met à jour le contenu de celles qui existent déjà, ne touche
    jamais `status`/`validated_by`/`validated_at` d'une proposition déjà revue par un humain.

    `merge` (pour "create" uniquement) : `finding["flows"]` fusionné avec `existing.flows`
    plutôt que remplacé. Nécessaire quand `run()` a été appelé avec `since` (cf.
    run_for_cycle) : dans ce cas, `finding["flows"]` n'est qu'une tranche partielle (les flux
    nouvellement approuvés depuis le cycle précédent), pas la vérité complète -- un
    remplacement ferait disparaître les flux déjà rattachés à un cycle antérieur. `merge=False`
    (rescan complet, `since=None`) garde le remplacement d'origine : `finding["flows"]` est
    alors la liste complète et à jour, remplacer permet de retirer un flux qui ne correspond
    plus (ex. re-bloqué depuis), ce qu'une fusion ne ferait jamais.
    """
    created, updated = 0, 0
    for finding in findings:
        identity = {
            "source": finding["source"], "intent": finding["intent"],
            "ingress_zone": finding["ingress_zone"], "egress_zone": finding["egress_zone"],
            "protocol": finding["protocol"], "dst_port": finding["dst_port"],
            "target_rule_name": finding["target_rule_name"],
        }
        existing = session.query(AclProposal).filter_by(**identity).one_or_none()
        if existing is None:
            session.add(
                AclProposal(
                    **identity,
                    proposed_action=finding["proposed_action"],
                    suggested_rule_name=finding["suggested_rule_name"],
                    src_networks=finding["src_networks"],
                    dst_networks=finding["dst_networks"],
                    source_recommendation_id=finding["source_recommendation_id"],
                    rationale=finding["rationale"],
                    proposed_rule_text=finding["proposed_rule_text"],
                    flows=finding["flows"],
                )
            )
            created += 1
        else:
            if finding["intent"] == "create" and finding["flows"]:
                merged_flows = (
                    list({f.id: f for f in existing.flows + finding["flows"]}.values()) if merge else finding["flows"]
                )
                src_networks = network_summary(sorted({f.src_ip for f in merged_flows}))
                dst_networks = network_summary(sorted({f.dst_ip for f in merged_flows}))
                existing.flows = merged_flows
                existing.src_networks = src_networks
                existing.dst_networks = dst_networks
                rationale = dict(finding["rationale"])
                rationale["flow_ids"] = [f.id for f in merged_flows]
                rationale["distinct_src_ip"] = src_networks["count"]
                rationale["distinct_dst_ip"] = dst_networks["count"]
                existing.rationale = rationale
                existing.proposed_rule_text = _format_create_rule_text(
                    existing.suggested_rule_name, finding["ingress_zone"], finding["egress_zone"],
                    finding["protocol"], finding["dst_port"], src_networks, dst_networks, merged_flows,
                )
            else:
                existing.src_networks = finding["src_networks"]
                existing.dst_networks = finding["dst_networks"]
                existing.rationale = finding["rationale"]
                existing.proposed_rule_text = finding["proposed_rule_text"]
            existing.source_recommendation_id = finding["source_recommendation_id"]
            updated += 1

    session.commit()
    return {"total_proposals": len(findings), "created": created, "updated": updated}

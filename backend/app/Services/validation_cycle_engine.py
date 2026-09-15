"""Cycle de validation périodique : compare la Matrice Réelle (état courant des Flow,
déjà dynamique) à la dernière Matrice Validée (snapshot figé au dernier ValidationCycle
clôturé **de la même source**), pour ne faire revoir au Responsable Réseau que ce qui a
changé depuis. Demande directe de l'encadrant (2026-08-19), révisée le 2026-08-21 après
démo -- voir docs/13-cycle-de-validation.md pour la conception complète et l'écart avec la
V1 initiale (cycle global -> cycle par source).

Réutilise directement flow_filters (mêmes filtres que /api/flows et /api/matrix) et
matrix_engine.DIMENSIONS/axis_expression/UNSET_LABEL pour le rollup par cellule -- jamais
une deuxième définition de zone/dérivés susceptible de diverger de la vraie Matrice.
"""

import collections
import ipaddress
from typing import Optional

from sqlalchemy.orm import Session

from ..flow_filters import FLOW_SEARCH_COLUMNS, apply_filters
from ..flows_query import apply_cell_filter
from ..models import Flow, FlowSnapshot, FlowValidationHistory, NetworkPolicy, RuleEnforcementClaim, ValidationCycle
from ..search_utils import apply_keyword_search
from ..time_utils import utcnow
from . import matrix_engine, subnet_observation
from .qualification_engine import COMMON_SAFE_PORTS, SENSITIVE_PORTS, UNCLASSIFIED_ROLE, ZONE_ROLES


def _ip_in_network(ip_str: Optional[str], network: "ipaddress.IPv4Network | ipaddress.IPv6Network") -> bool:
    """IP invalide/vide -> jamais dans le réseau (silencieux, ne casse jamais le filtrage des
    autres Flow) -- même principe de tolérance que subnet_observation.cidr_for_ip."""
    if not ip_str:
        return False
    try:
        return ipaddress.ip_address(ip_str) in network
    except ValueError:
        return False

# Champs dont un changement signifie "à revalider" (comparés snapshot vs état courant).
# occurrence_count/allow_count/block_count sont volontairement EXCLUS : un flux déjà validé
# qui continue simplement d'être vu plus souvent n'a rien de nouveau à décider -- même
# principe que la fréquence conditionnelle du Qualification Engine (docs/07, itération 2) :
# le volume seul est du bruit, pas un signal. Affichés en contexte, jamais un critère de diff.
#
# "cycle_dominant_action" (pas "dominant_action") depuis le 2026-09-06 -- bug réel trouvé :
# dominant_action est un cumul LIFETIME, jamais réinitialisé ; une seule occurrence
# contradictoire n'importe quand dans l'histoire du flow (même des cycles plus tôt) le
# contamine en "Mixed" pour toujours, même si le comportement du cycle en cours est
# parfaitement tranché. cycle_dominant_action (Flow.cycle_*, remis à zéro à chaque
# close_cycle()) compare toujours deux fenêtres "depuis la dernière clôture", jamais pollué
# par une histoire plus ancienne. dominant_action (lifetime) reste utilisé ailleurs (Table
# des flux, Qualification Engine) -- jamais retiré, juste plus comparé ici.
STRUCTURAL_FIELDS: tuple[str, ...] = (
    "cycle_dominant_action",
    "ingress_zone",
    "egress_zone",
    "last_access_control_rule_name",
    "criticality_label",
)

# Champs figés dans FlowSnapshot à la clôture -- doit rester synchronisé avec les colonnes
# du modèle FlowSnapshot (hors id/cycle_id/flow_id) : une seule liste, jamais deux définitions
# susceptibles de diverger entre close_cycle() et le modèle. "dominant_action" (lifetime) est
# ajouté explicitement ici (pas dans STRUCTURAL_FIELDS -- jamais comparé au diff, cf.
# cycle_dominant_action) car compute_validated_matrix en a besoin (axe "Zone × Action" de la
# Matrice Validée). Les autres champs bytes/durée/application ne servent jamais au diff --
# uniquement à reconstruire une Matrice Validée fidèle (mêmes modes de coloration que la
# Matrice Réelle).
SNAPSHOT_FIELDS: tuple[str, ...] = STRUCTURAL_FIELDS + (
    "dominant_action",
    "occurrence_count",
    "allow_count",
    "block_count",
    "last_seen_at",
    "validation_status",
    "total_initiator_bytes",
    "total_responder_bytes",
    "total_connection_duration",
    "application_protocol",
    "decided_action",
    "cycle_occurrence_count",
    "cycle_allow_count",
    "cycle_block_count",
    "cycle_total_initiator_bytes",
    "cycle_total_responder_bytes",
    "cycle_total_connection_duration",
)

# Champs Flow.cycle_* remis à zéro sur CHAQUE Flow de la source au moment de la clôture,
# juste après les avoir figés dans FlowSnapshot (ci-dessus) -- la prochaine fenêtre "depuis
# la dernière clôture" doit repartir de zéro, jamais continuer d'accumuler depuis avant.
_CYCLE_COUNTER_RESET: dict[str, object] = {
    "cycle_occurrence_count": 0,
    "cycle_allow_count": 0,
    "cycle_block_count": 0,
    "cycle_dominant_action": None,
    "cycle_total_initiator_bytes": 0,
    "cycle_total_responder_bytes": 0,
    "cycle_total_connection_duration": 0,
}

DIFF_STATUSES: tuple[str, ...] = ("nouveau", "disparu", "regle_non_appliquee", "modifie", "conforme")

# "disparu" (pas revu depuis la baseline) n'est PAS un écart à traiter -- décision actée le
# 2026-08-21 après retour de l'encadrant : son workflow ne décrit que deux cas ("identique ->
# conforme", "nouveau -> à valider"), jamais un troisième "équipement resté silencieux".
# Gardé comme statut à part entière (filtrable, informationnel) mais explicitement exclu de
# tout ce qui compte comme "à traiter" -- ECARTS_A_TRAITER en est la seule définition, jamais
# recalculée séparément ailleurs (frontend compris, cf. ValidationCyclePage.tsx).
# "regle_non_appliquee" ajouté le 2026-09-03 : une décision explicite (Flow.decided_action)
# existait au cycle précédent et l'action observée ne s'y conforme toujours pas -- un écart
# à traiter, prioritaire même (cf. diff_for_flow), jamais noyé avec un simple "modifie".
ECARTS_A_TRAITER: tuple[str, ...] = ("nouveau", "modifie", "regle_non_appliquee")


def get_latest_cycle(session: Session, source: str) -> Optional[ValidationCycle]:
    return (
        session.query(ValidationCycle)
        .filter(ValidationCycle.source == source)
        .order_by(ValidationCycle.closed_at.desc())
        .first()
    )


def previous_cycle_for(session: Session, cycle: ValidationCycle) -> Optional[ValidationCycle]:
    """Le cycle qui précédait `cycle` pour sa source -- utilisé par l'ACL Engine pour borner
    la fenêtre "flux approuvés depuis la dernière génération" (cf. run_for_cycle). Résolution
    sans état supplémentaire : uniquement `source` + `closed_at`, toujours cohérent même
    longtemps après la clôture.
    """
    return (
        session.query(ValidationCycle)
        .filter(ValidationCycle.source == cycle.source, ValidationCycle.closed_at < cycle.closed_at)
        .order_by(ValidationCycle.closed_at.desc())
        .first()
    )


def _latest_cycles_by_source(session: Session, sources: set[str]) -> dict[str, ValidationCycle]:
    """Le dernier ValidationCycle de chaque source présente dans `sources` -- une requête
    par source (leur nombre reste petit, quelques firewalls) plutôt qu'une seule requête SQL
    à fenêtre, pour rester lisible ; jamais mélanger deux sources dans un même cycle.
    """
    result = {}
    for source in sources:
        cycle = get_latest_cycle(session, source)
        if cycle is not None:
            result[source] = cycle
    return result


def _snapshot_map(session: Session, cycle_id: int) -> dict[int, FlowSnapshot]:
    rows = session.query(FlowSnapshot).filter(FlowSnapshot.cycle_id == cycle_id).all()
    return {s.flow_id: s for s in rows if s.flow_id is not None}


def diff_for_flow(flow: Flow, snapshot: Optional[FlowSnapshot]) -> dict:
    """Fonction pure : ne touche pas la base. Retourne {"status": ..., "details": {...} | None}.

    - Pas de snapshot pour ce Flow -> "nouveau" (créé après la dernière baseline de sa
      source, ou tout premier cycle de cette source : aucune baseline n'existe encore).
    - Snapshot présent mais Flow.last_seen_at n'a pas avancé depuis -> "disparu" : aucune
      nouvelle observation depuis la baseline. Les Flow ne sont JAMAIS supprimés (règle
      absolue du projet) -- "disparu" ne veut donc jamais dire "la ligne n'existe plus", mais
      "plus revu depuis la dernière validation". Informationnel uniquement, cf.
      ECARTS_A_TRAITER -- jamais compté comme un écart à valider.
    - Snapshot présent, Flow revu depuis, ET une décision explicite existait
      (`snapshot.decided_action`) mais l'action réellement observée CE CYCLE
      (`flow.cycle_dominant_action`, pas le cumul lifetime -- voir STRUCTURAL_FIELDS) ne s'y
      conforme toujours pas -> "regle_non_appliquee" (2026-09-03, priorité absolue sur
      "modifie" : une décision humaine déjà prise, toujours pas appliquée par le pare-feu,
      distincte d'une simple dérive organique du trafic que personne n'a décidée).
    - Sinon (pas de décision en attente, ou décision déjà honorée) -> "modifie" si au moins
      un champ structurant diffère, sinon "conforme" (diff = 0, rien à faire). Une décision
      honorée mais accompagnée d'un autre changement structurant (ex. la zone a aussi bougé)
      remonte donc quand même en "modifie", jamais silencieusement absorbée en "conforme" --
      MAIS `cycle_dominant_action` lui-même est exclu de cette 2e comparaison dans ce cas :
      son changement (Allow -> Block décidé, par exemple) est déjà entièrement expliqué par
      la décision honorée, jamais reproposé comme un "modifie" en plus (bug réel trouvé en
      testant : sans cette exclusion, une décision honorée ressortait toujours "modifie",
      jamais "conforme", puisque ce champ fait aussi partie de STRUCTURAL_FIELDS).

    `cycle_dominant_action` (pas `dominant_action`) partout ci-dessus, 2026-09-06 : voir le
    commentaire sur STRUCTURAL_FIELDS -- une comparaison lifetime resterait polluée pour
    toujours par une seule occurrence contradictoire ancienne, même hors de ce cycle.
    """
    if snapshot is None:
        return {"status": "nouveau", "details": None}

    reobserved = (
        flow.last_seen_at is not None
        and snapshot.last_seen_at is not None
        and flow.last_seen_at > snapshot.last_seen_at
    )
    if not reobserved:
        return {"status": "disparu", "details": None}

    decision_pending = snapshot.decided_action is not None
    if decision_pending and flow.cycle_dominant_action != snapshot.decided_action:
        detail = {"avant": snapshot.decided_action, "apres": flow.cycle_dominant_action}
        # Répartition chiffrée jamais le mot brut "Mixed" (2026-09-06) -- avant est toujours
        # un decided_action propre ("Allow"/"Block", jamais "Mixed"), seul apres peut l'être.
        if flow.cycle_dominant_action == "Mixed":
            detail["apres_allow"] = flow.cycle_allow_count
            detail["apres_block"] = flow.cycle_block_count
        return {"status": "regle_non_appliquee", "details": {"decided_action": detail}}

    fields_to_check = (
        tuple(f for f in STRUCTURAL_FIELDS if f != "cycle_dominant_action") if decision_pending else STRUCTURAL_FIELDS
    )
    changes = {}
    for field in fields_to_check:
        before = getattr(snapshot, field)
        after = getattr(flow, field)
        if before != after:
            change = {"avant": before, "apres": after}
            # Répartition chiffrée jamais le mot brut "Mixed" (2026-09-06) -- le frontend a
            # besoin des comptes Allow/Block du côté concerné pour l'afficher, la valeur
            # seule ("Mixed") ne suffit pas. Uniquement pour ce champ, et seulement le(s)
            # côté(s) effectivement "Mixed" : les autres champs (zones, règle, criticité)
            # sont déjà des valeurs présentables telles quelles.
            if field == "cycle_dominant_action":
                if before == "Mixed":
                    change["avant_allow"] = snapshot.cycle_allow_count
                    change["avant_block"] = snapshot.cycle_block_count
                if after == "Mixed":
                    change["apres_allow"] = flow.cycle_allow_count
                    change["apres_block"] = flow.cycle_block_count
            changes[field] = change

    if changes:
        return {"status": "modifie", "details": changes}
    return {"status": "conforme", "details": None}


def compute_diff(
    session: Session,
    filters: dict,
    q: Optional[str] = None,
    src_cidr: Optional[str] = None,
    *,
    dimension: Optional[str] = None,
    row_value: Optional[str] = None,
    col_value: Optional[str] = None,
) -> tuple[list[tuple[Flow, dict]], dict, dict[str, ValidationCycle]]:
    """Diff de TOUS les Flow correspondant aux filtres simples (pas de pagination ici --
    gérée par l'appelant, cf. validation_cycle_query.py). Chaque Flow est comparé à la
    dernière baseline **de sa propre source** -- jamais celle d'une autre (un cycle ne
    mélange jamais deux sources). `q` (mot-clé, demande de l'encadrant 2026-08-25) réutilise
    exactement FLOW_SEARCH_COLUMNS de flow_filters.py -- même colonnes que la Table des flux,
    jamais une deuxième définition. Retourne (paires (flow, diff), résumé des comptages par
    statut + nombre d'écarts encore en attente de revue humaine, cycles utilisés par source
    -- {} si aucune des sources présentes n'a de baseline).

    `src_cidr` (2026-09-11, demande de l'encadrant -- fusion de la page "Politiques de
    sous-réseau" dans le Cycle de validation) : optionnel, restreint aux Flow dont `src_ip`
    tombe dans ce réseau -- utilisé par le bouton "+" d'une ligne de sous-réseau pour déplier
    EXACTEMENT ce même diff, juste filtré. Absent (comportement par défaut, donc TOUTE la
    Table des flux/le Cycle de validation existants) -> zéro changement de comportement,
    aucune régression. Filtrage fait en Python (pas en SQL, pas d'opérateur CIDR natif en
    SQLite) via ipaddress, silencieux sur une IP invalide plutôt que de faire échouer le
    calcul -- même principe que Services/subnet_observation.py::cidr_for_ip.

    `dimension`/`row_value`/`col_value` (2026-09-12, demande de l'encadrant) : optionnels,
    restreignent à une cellule précise de la Matrice Réelle -- réutilise
    flows_query.apply_cell_filter (même filtre de cellule ET même exclusion des Flow inactifs
    depuis la dernière clôture, `Flow.cycle_occurrence_count > 0`, que build_matrix()) pour
    que le tiroir de détail d'une cellule en mode "Colorer par écart" puisse annoter chaque
    flux affiché de son statut d'écart, sans jamais en révéler un absent de la cellule.
    """
    flows = apply_cell_filter(
        apply_keyword_search(apply_filters(session.query(Flow), filters), q, FLOW_SEARCH_COLUMNS),
        dimension, row_value, col_value,
    ).order_by(Flow.id).all()

    if src_cidr is not None:
        try:
            network = ipaddress.ip_network(src_cidr, strict=False)
        except ValueError as exc:
            raise ValueError(f"src_cidr invalide : {src_cidr!r}") from exc
        flows = [f for f in flows if _ip_in_network(f.src_ip, network)]

    sources = {f.source for f in flows if f.source is not None}
    cycles_by_source = _latest_cycles_by_source(session, sources)
    snapshots_by_cycle = {
        cycle.id: _snapshot_map(session, cycle.id) for cycle in cycles_by_source.values()
    }

    pairs: list[tuple[Flow, dict]] = []
    summary: collections.Counter = collections.Counter()
    pending_review_count = 0
    for flow in flows:
        cycle = cycles_by_source.get(flow.source) if flow.source else None
        snapshot = snapshots_by_cycle[cycle.id].get(flow.id) if cycle else None
        diff = diff_for_flow(flow, snapshot)
        pairs.append((flow, diff))
        summary[diff["status"]] += 1
        if diff["status"] in ECARTS_A_TRAITER and flow.validation_status == "pending":
            pending_review_count += 1

    summary_out = {status: summary.get(status, 0) for status in DIFF_STATUSES}
    summary_out["pending_review_count"] = pending_review_count

    _ensure_claims_detected(session, pairs)

    return pairs, summary_out, cycles_by_source


def _ensure_claims_detected(session: Session, pairs: list[tuple[Flow, dict]]) -> None:
    """Effet de bord DÉLIBÉRÉ sur ce chemin de lecture (2026-09-10, demande de l'encadrant) --
    la toute première fois qu'un Flow est vu "regle_non_appliquee" par CE calcul de diff, une
    ligne de suivi léger (`RuleEnforcementClaim`) est créée avec `first_detected_at` =
    maintenant, AVANT même qu'un humain ne clique "Déclarer la réclamation" (app/
    rule_enforcement_claims.py, qui ne touche que `last_claimed_at`/`claim_count`). Sans ça,
    "première détection" et "première réclamation" seraient toujours la même date, ce qui
    viderait le champ de son sens. Idempotent -- ne touche jamais une ligne déjà existante,
    jamais de doublon (flow_id est UNIQUE), jamais écrasée par un appel ultérieur. Un des
    seuls effets de bord sur un chemin de lecture dans ce projet, documenté pour cette raison.
    """
    flow_ids_needing_claim = [flow.id for flow, diff in pairs if diff["status"] == "regle_non_appliquee"]
    if not flow_ids_needing_claim:
        return

    existing_flow_ids = {
        row[0]
        for row in session.query(RuleEnforcementClaim.flow_id)
        .filter(RuleEnforcementClaim.flow_id.in_(flow_ids_needing_claim))
        .all()
    }
    new_flow_ids = [fid for fid in flow_ids_needing_claim if fid not in existing_flow_ids]
    if not new_flow_ids:
        return

    now = utcnow()
    for flow_id in new_flow_ids:
        session.add(RuleEnforcementClaim(flow_id=flow_id, first_detected_at=now, claim_count=0))
    session.commit()


def compute_cell_diff(session: Session, dimension: str, filters: dict) -> dict:
    """Rollup du diff par cellule de matrice, pour la même dimension/les mêmes filtres que
    GET /api/matrix -- réutilise directement matrix_engine.axis_expression/DIMENSIONS (les
    expressions SQL exactes qui construisent la vraie Matrice), jamais une deuxième logique
    de regroupement zone/dérivés susceptible de diverger.
    """
    if dimension not in matrix_engine.DIMENSIONS:
        raise ValueError(f"Dimension inconnue : {dimension!r}. Valeurs possibles : {sorted(matrix_engine.DIMENSIONS)}")

    row_field, col_field = matrix_engine.DIMENSIONS[dimension]
    row_col = matrix_engine.axis_expression(row_field).label("row")
    col_col = matrix_engine.axis_expression(col_field).label("col")

    rows = apply_filters(session.query(Flow, row_col, col_col), filters).all()

    sources = {flow.source for flow, _, _ in rows if flow.source is not None}
    cycles_by_source = _latest_cycles_by_source(session, sources)
    snapshots_by_cycle = {
        cycle.id: _snapshot_map(session, cycle.id) for cycle in cycles_by_source.values()
    }

    cell_counts: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    for flow, row_label, col_label in rows:
        cycle = cycles_by_source.get(flow.source) if flow.source else None
        snapshot = snapshots_by_cycle[cycle.id].get(flow.id) if cycle else None
        diff = diff_for_flow(flow, snapshot)
        key = (
            str(row_label) if row_label is not None else matrix_engine.UNSET_LABEL,
            str(col_label) if col_label is not None else matrix_engine.UNSET_LABEL,
        )
        cell_counts[key][diff["status"]] += 1

    cells = [
        {"row": row, "col": col, "diff_summary": {status: counts.get(status, 0) for status in DIFF_STATUSES}}
        for (row, col), counts in cell_counts.items()
    ]
    return {"cycles": cycles_by_source, "cells": cells}


def compute_subnet_diff(session: Session, *, source: str, prefix_length: int) -> dict:
    """Rollup du diff par sous-réseau CIDR observé (2026-09-11, demande de l'encadrant --
    fusion de la page "Politiques de sous-réseau" dans le Cycle de validation) : même rôle que
    compute_cell_diff ci-dessus, mais regroupe par CIDR de `src_ip` (via
    Services/subnet_observation.py::cidr_for_ip, MÊME regroupement suggestif que
    /network-policies -- jamais une deuxième implémentation) plutôt que par cellule de
    matrice. Réutilise compute_diff (déjà testé) pour TOUTE la source, sans filtre
    supplémentaire -- les totaux par sous-réseau doivent rester vrais même quand aucune ligne
    n'est dépliée, cf. ValidationCyclePage.tsx (StatTiles alimentées séparément, pas dérivées
    de ce rollup, pour ne jamais silencieusement perdre les Flow à IP invalide/IPv6 qui, eux,
    n'apparaissent dans aucun bucket ici).
    """
    if not (subnet_observation.MIN_PREFIX_LENGTH <= prefix_length <= subnet_observation.MAX_PREFIX_LENGTH):
        raise ValueError(
            f"prefix_length doit être entre {subnet_observation.MIN_PREFIX_LENGTH} et {subnet_observation.MAX_PREFIX_LENGTH}"
        )

    pairs, _summary, cycles_by_source = compute_diff(session, {"source": source})

    buckets: dict[str, dict] = collections.defaultdict(
        lambda: {"machines": set(), "flow_count": 0, "diff_summary": collections.Counter(), "network": None}
    )
    for flow, diff in pairs:
        cidr = subnet_observation.cidr_for_ip(flow.src_ip, prefix_length)
        if cidr is None:
            continue
        bucket = buckets[cidr]
        bucket["machines"].add(flow.src_ip)
        bucket["flow_count"] += 1
        bucket["diff_summary"][diff["status"]] += 1
        bucket["network"] = ipaddress.ip_network(cidr)

    items = [
        {
            "cidr": cidr,
            "machine_count": len(bucket["machines"]),
            "flow_count": bucket["flow_count"],
            "diff_summary": {status: bucket["diff_summary"].get(status, 0) for status in DIFF_STATUSES},
        }
        for cidr, bucket in buckets.items()
    ]
    items.sort(key=lambda item: buckets[item["cidr"]]["network"])

    return {"source": source, "prefix_length": prefix_length, "cycle": cycles_by_source.get(source), "items": items}


def close_cycle(session: Session, source: str, closed_by: Optional[str] = None, note: Optional[str] = None) -> ValidationCycle:
    """Clôture le cycle courant **d'une source précise** : fige l'état de tous ses Flow
    actuels dans un nouveau ValidationCycle, qui devient la nouvelle référence pour le
    prochain diff de cette même source -- n'affecte jamais la baseline d'une autre source.
    Jamais de blocage technique si des écarts restent en attente de revue (avertissement doux
    côté interface uniquement, décision actée) -- toujours une décision humaine libre, jamais
    un verrou dur.
    """
    flows = session.query(Flow).filter(Flow.source == source).all()

    cycle = ValidationCycle(source=source, closed_by=closed_by, closed_at=utcnow(), note=note, flow_count=len(flows))
    session.add(cycle)
    session.flush()  # obtenir cycle.id avant de créer les FlowSnapshot

    for flow in flows:
        session.add(
            FlowSnapshot(
                cycle_id=cycle.id,
                flow_id=flow.id,
                **{field: getattr(flow, field) for field in SNAPSHOT_FIELDS},
            )
        )
        # Remise à zéro des compteurs "depuis la dernière clôture" -- APRÈS les avoir figés
        # ci-dessus dans le FlowSnapshot, jamais avant. La prochaine fenêtre commence ici.
        for field, reset_value in _CYCLE_COUNTER_RESET.items():
            setattr(flow, field, reset_value)

    session.commit()
    session.refresh(cycle)
    return cycle


# --- Matrice Validée : reconstruire une vraie matrice depuis les snapshots figés ------------
#
# Jusqu'ici la "Matrice Validée" n'existait que comme donnée interne servant au diff --
# jamais consultable telle quelle. Demande explicite de Loulou (2026-08-21, après confusion
# sur "où est la Matrice Validée ?") : une vraie page miroir de la Matrice Réelle, construite
# à partir des mêmes FlowSnapshot, avec les mêmes modes de coloration.

# "timeslot_zone" est la seule dimension non reconstructible : first_seen_at n'est jamais
# figé dans FlowSnapshot (la dimension est de toute façon déjà gardée derrière un seuil
# d'observation ailleurs, cf. matrix_engine.TIME_GATED_DIMENSIONS -- non prioritaire à figer).
SNAPSHOT_EXCLUDED_DIMENSIONS = frozenset({"timeslot_zone"})
SNAPSHOT_DIMENSIONS: tuple[str, ...] = tuple(d for d in matrix_engine.DIMENSIONS if d not in SNAPSHOT_EXCLUDED_DIMENSIONS)

# Champs mutables figés directement dans FlowSnapshot vs. champs d'identité stables lus sur
# le Flow associé (source/src_ip/dst_ip/dst_port/protocol ne changent jamais pour un flow_id
# donné, cf. uq_flow_identity -- jamais besoin de les figer séparément).
_SNAPSHOT_SOURCED_FIELDS = frozenset(
    {"ingress_zone", "egress_zone", "dominant_action", "last_access_control_rule_name", "criticality_label", "validation_status", "application_protocol"}
)
_FLOW_SOURCED_FIELDS = frozenset({"source", "src_ip", "dst_ip", "dst_port", "protocol"})


def _direction_value(ingress_zone: Optional[str], egress_zone: Optional[str]) -> str:
    # Même classification que matrix_engine._direction_expression (ZONE_ROLES, docs/07) --
    # réutilise les mêmes constantes, jamais une deuxième classification. Version Python
    # (au lieu d'une expression SQL) car évaluée ligne par ligne sur des FlowSnapshot déjà
    # chargés en mémoire, pas via une requête agrégée.
    ingress_role = ZONE_ROLES.get(ingress_zone, UNCLASSIFIED_ROLE) if ingress_zone else UNCLASSIFIED_ROLE
    egress_role = ZONE_ROLES.get(egress_zone, UNCLASSIFIED_ROLE) if egress_zone else UNCLASSIFIED_ROLE
    return f"{ingress_role}_vers_{egress_role}"


def _port_category_value(dst_port: Optional[int]) -> str:
    # Même classification que matrix_engine._port_category_expression (SENSITIVE_PORTS/
    # COMMON_SAFE_PORTS, docs/07) -- mêmes constantes, version Python pour la même raison
    # que _direction_value ci-dessus.
    if dst_port in SENSITIVE_PORTS:
        return "port_sensible"
    if dst_port in COMMON_SAFE_PORTS:
        return "port_courant"
    return "port_non_classifie"


def _snapshot_field_value(field_name: str, snapshot: FlowSnapshot, flow: Optional[Flow]):
    if field_name in _SNAPSHOT_SOURCED_FIELDS:
        return getattr(snapshot, field_name)
    if field_name in _FLOW_SOURCED_FIELDS:
        return getattr(flow, field_name) if flow is not None else None
    if field_name == "direction":
        return _direction_value(snapshot.ingress_zone, snapshot.egress_zone)
    if field_name == "port_category":
        return _port_category_value(flow.dst_port if flow is not None else None)
    raise ValueError(f"Champ non calculable depuis un FlowSnapshot : {field_name!r}")


def compute_validated_matrix(session: Session, source: str, dimension: str) -> dict:
    """Reconstruit la Matrice Validée -- pas un diff, la matrice elle-même -- à partir du
    dernier ValidationCycle clôturé pour `source`, en utilisant les valeurs FIGÉES dans
    FlowSnapshot plutôt que l'état courant des Flow. Même forme de cellule que
    matrix_engine.build_matrix (flow_count/allow_count/block_count/total_bytes/
    total_duration_seconds/criticality_breakdown), pour être affichée par le même composant
    MatrixGrid côté frontend -- jamais une deuxième représentation de matrice. `cycle=None`
    si aucun cycle n'a encore été clôturé pour cette source (matrice vide, pas une erreur).
    """
    if dimension not in matrix_engine.DIMENSIONS:
        raise ValueError(f"Dimension inconnue : {dimension!r}. Valeurs possibles : {sorted(matrix_engine.DIMENSIONS)}")
    if dimension in SNAPSHOT_EXCLUDED_DIMENSIONS:
        raise ValueError(f"Dimension {dimension!r} non disponible pour la Matrice Validée (champ jamais figé au moment de la clôture).")

    cycle = get_latest_cycle(session, source)
    if cycle is None:
        return {"cycle": None, "cells": []}

    row_field, col_field = matrix_engine.DIMENSIONS[dimension]

    snapshots = session.query(FlowSnapshot).filter(FlowSnapshot.cycle_id == cycle.id).all()
    flow_ids = [s.flow_id for s in snapshots if s.flow_id is not None]
    flows_by_id = {f.id: f for f in session.query(Flow).filter(Flow.id.in_(flow_ids)).all()} if flow_ids else {}

    cell_map: dict[tuple[str, str], dict] = {}
    for snapshot in snapshots:
        flow = flows_by_id.get(snapshot.flow_id)
        row_value = _snapshot_field_value(row_field, snapshot, flow)
        col_value = _snapshot_field_value(col_field, snapshot, flow)
        row_label = str(row_value) if row_value is not None else matrix_engine.UNSET_LABEL
        col_label = str(col_value) if col_value is not None else matrix_engine.UNSET_LABEL

        cell = cell_map.setdefault(
            (row_label, col_label),
            {
                "row": row_label, "col": col_label, "flow_count": 0, "allow_count": 0, "block_count": 0,
                "total_bytes": 0, "total_duration_seconds": 0, "criticality_breakdown": {},
            },
        )
        cell["flow_count"] += 1
        cell["allow_count"] += snapshot.allow_count
        cell["block_count"] += snapshot.block_count
        cell["total_bytes"] += snapshot.total_initiator_bytes + snapshot.total_responder_bytes
        cell["total_duration_seconds"] += snapshot.total_connection_duration
        label = snapshot.criticality_label or "non_qualifie"
        cell["criticality_breakdown"][label] = cell["criticality_breakdown"].get(label, 0) + 1

    return {"cycle": cycle, "cells": list(cell_map.values())}


# --- Drill-down d'une cellule de la Matrice Validée : lister les Flow TELS QU'ILS ÉTAIENT --
#
# Demande explicite de l'encadrant (2026-09-09) : rendre les cellules de la Matrice Validée
# cliquables comme la Matrice Réelle -- ça avait été délibérément exclu le 2026-08-21 (cliquer
# une cellule y aurait montré des Flow VIVANTS pour un état figé passé, trompeur). Résolu ici
# en lisant FlowSnapshot plutôt que Flow : la liste reste fidèle à ce que montrait la cellule
# au moment de la clôture, même si les Flow ont changé depuis.

FLOW_SNAPSHOT_CELL_DEFAULT_LIMIT = 200
FLOW_SNAPSHOT_CELL_MAX_LIMIT = 1000


def _summarize_snapshots(pairs: list[tuple[FlowSnapshot, Flow]]) -> dict:
    """Même convention que flows_query._summarize (flow-count par dominant_action figé,
    "Mixed" compté dans allow ET block) -- pour que FlowsSummaryBar affiche exactement la
    même chose côté frontend, que la source soit un Flow en direct ou un FlowSnapshot figé."""
    allow_count = 0
    block_count = 0
    criticality_breakdown: dict[str, int] = {}
    for snapshot, _ in pairs:
        if snapshot.dominant_action in ("Allow", "Mixed"):
            allow_count += 1
        if snapshot.dominant_action in ("Block", "Mixed"):
            block_count += 1
        label = snapshot.criticality_label or "non_qualifie"
        criticality_breakdown[label] = criticality_breakdown.get(label, 0) + 1
    return {
        "total_flows": len(pairs),
        "allow_count": allow_count,
        "block_count": block_count,
        "criticality_breakdown": criticality_breakdown,
    }


def _snapshot_as_flow_out(snapshot: FlowSnapshot, flow: Flow) -> dict:
    """Reconstruit un objet forme-FlowOut à partir d'un FlowSnapshot figé -- réutilise le même
    schéma FlowOut côté API pour que le frontend réutilise FlowsTable tel quel (demande de
    l'encadrant, 2026-09-09), sans composant de rendu dupliqué. Champs d'identité
    (source/src_ip/dst_ip/dst_port/protocol) lus sur le Flow associé -- ne changent jamais
    pour un flow_id donné (uq_flow_identity), jamais besoin de les figer séparément. Les
    champs JAMAIS figés dans FlowSnapshot (validated_by, validated_at, criticality_score,
    security_status, web_application, first_seen_at) restent explicitement None : ce
    drill-down est rendu en LECTURE SEULE (readOnly sur FlowsTable, cf. FlowsTable.tsx) --
    ces champs ne sont jamais affichés ni utilisés pour une décision, jamais fabriqués pour
    paraître réels.
    """
    return {
        "id": flow.id,
        "source": flow.source,
        "src_ip": flow.src_ip,
        "dst_ip": flow.dst_ip,
        "dst_port": flow.dst_port,
        "protocol": flow.protocol,
        "dominant_action": snapshot.dominant_action,
        "occurrence_count": snapshot.occurrence_count,
        "allow_count": snapshot.allow_count,
        "block_count": snapshot.block_count,
        "total_initiator_bytes": snapshot.total_initiator_bytes,
        "total_responder_bytes": snapshot.total_responder_bytes,
        "first_seen_at": None,
        "last_seen_at": snapshot.last_seen_at,
        "ingress_zone": snapshot.ingress_zone,
        "egress_zone": snapshot.egress_zone,
        "application_protocol": snapshot.application_protocol,
        "web_application": None,
        "last_access_control_rule_name": snapshot.last_access_control_rule_name,
        "criticality_score": None,
        "criticality_label": snapshot.criticality_label,
        "security_status": None,
        "validation_status": snapshot.validation_status,
        "validated_by": None,
        "validated_at": None,
        "decided_action": snapshot.decided_action,
        "cycle_occurrence_count": snapshot.cycle_occurrence_count,
        "cycle_allow_count": snapshot.cycle_allow_count,
        "cycle_block_count": snapshot.cycle_block_count,
        "cycle_dominant_action": snapshot.cycle_dominant_action,
        "cycle_total_initiator_bytes": snapshot.cycle_total_initiator_bytes,
        "cycle_total_responder_bytes": snapshot.cycle_total_responder_bytes,
        "cycle_total_connection_duration": snapshot.cycle_total_connection_duration,
    }


def list_flow_snapshots_for_cell(
    session: Session,
    *,
    cycle_id: int,
    dimension: str,
    row_value: str,
    col_value: str,
    limit: int = FLOW_SNAPSHOT_CELL_DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    """Flow d'une cellule précise de la Matrice Validée, reconstruits depuis FlowSnapshot --
    jamais depuis l'état courant de Flow (voir bandeau de commentaire ci-dessus). Réutilise
    _snapshot_field_value (même fonction que compute_validated_matrix) pour classer chaque
    snapshot par cellule : rigoureusement la même logique que celle qui a construit la grille,
    jamais une deuxième classification susceptible de diverger. Pas de filtrage SQL direct --
    row_value/col_value peuvent dépendre d'une dimension dérivée (direction, port_category),
    calculée en Python comme le fait déjà compute_validated_matrix.
    """
    if dimension not in matrix_engine.DIMENSIONS:
        raise ValueError(f"Dimension inconnue : {dimension!r}. Valeurs possibles : {sorted(matrix_engine.DIMENSIONS)}")
    if dimension in SNAPSHOT_EXCLUDED_DIMENSIONS:
        raise ValueError(f"Dimension {dimension!r} non disponible pour la Matrice Validée (champ jamais figé au moment de la clôture).")

    row_field, col_field = matrix_engine.DIMENSIONS[dimension]

    snapshots = session.query(FlowSnapshot).filter(FlowSnapshot.cycle_id == cycle_id).all()
    flow_ids = [s.flow_id for s in snapshots if s.flow_id is not None]
    flows_by_id = {f.id: f for f in session.query(Flow).filter(Flow.id.in_(flow_ids)).all()} if flow_ids else {}

    matching: list[tuple[FlowSnapshot, Flow]] = []
    for snapshot in snapshots:
        flow = flows_by_id.get(snapshot.flow_id)
        if flow is None:
            continue  # jamais censé arriver (Flow jamais supprimé, cf. règle absolue du projet) -- filet de sécurité
        row_value_actual = _snapshot_field_value(row_field, snapshot, flow)
        col_value_actual = _snapshot_field_value(col_field, snapshot, flow)
        row_label = str(row_value_actual) if row_value_actual is not None else matrix_engine.UNSET_LABEL
        col_label = str(col_value_actual) if col_value_actual is not None else matrix_engine.UNSET_LABEL
        if row_label == row_value and col_label == col_value:
            matching.append((snapshot, flow))

    total_count = len(matching)
    limit = max(1, min(limit, FLOW_SNAPSHOT_CELL_MAX_LIMIT))
    page = matching[offset : offset + limit]

    return {
        "items": [_snapshot_as_flow_out(snapshot, flow) for snapshot, flow in page],
        "total_count": total_count,
        "summary": _summarize_snapshots(matching),
    }


# --- Rapport de clôture de cycle (PDF) : régénéré à la demande, jamais persisté ------------
#
# Demande de l'encadrant (2026-09-10) : un PDF récapitulant toutes les décisions "Changer la
# règle" prises DURANT un cycle précis. Aucune nouvelle table -- FlowValidationHistory (déjà
# la trace en ajout seul de chaque décision) suffit, avec exactement la même fenêtre de temps
# "depuis le cycle précédent de cette source" que l'ACL Engine (Services/acl_engine.py::
# run_for_cycle) -- jamais une deuxième logique de scope susceptible de diverger. Toujours
# régénérable, toujours à jour même après coup (jamais un instantané figé qui pourrait devenir
# incohérent avec la trace elle-même).


def build_cycle_report(session: Session, cycle: ValidationCycle) -> list[tuple[FlowValidationHistory, Flow]]:
    """Décisions "Changer la règle" (justification non nulle) prises sur des Flow de
    `cycle.source`, depuis la clôture du cycle précédent de cette même source (exclue) jusqu'à
    la clôture de `cycle` (incluse) -- le premier cycle d'une source n'a pas de borne basse,
    toute l'historique jusqu'à cette clôture compte. Trié chronologiquement.
    """
    previous = previous_cycle_for(session, cycle)
    since = previous.closed_at if previous is not None else None

    query = (
        session.query(FlowValidationHistory, Flow)
        .join(Flow, FlowValidationHistory.flow_id == Flow.id)
        .filter(Flow.source == cycle.source, FlowValidationHistory.justification.isnot(None))
        .filter(FlowValidationHistory.created_at <= cycle.closed_at)
    )
    if since is not None:
        query = query.filter(FlowValidationHistory.created_at > since)

    return query.order_by(FlowValidationHistory.created_at).all()


def build_cycle_network_policies_report(session: Session, cycle: ValidationCycle) -> list[NetworkPolicy]:
    """Politiques de sous-réseau (`NetworkPolicy`) créées pour `cycle.source`, depuis la
    clôture du cycle précédent de cette même source (exclue) jusqu'à la clôture de `cycle`
    (incluse) -- même fenêtrage que build_cycle_report ci-dessus pour les décisions de flux
    (2026-09-14, demande de l'encadrant : les politiques de sous-réseau décidées durant un
    cycle doivent aussi apparaître dans son rapport de clôture, elles sont ignorées jusqu'ici).
    Trié chronologiquement.
    """
    previous = previous_cycle_for(session, cycle)
    since = previous.closed_at if previous is not None else None

    query = (
        session.query(NetworkPolicy)
        .filter(NetworkPolicy.source == cycle.source)
        .filter(NetworkPolicy.created_at <= cycle.closed_at)
    )
    if since is not None:
        query = query.filter(NetworkPolicy.created_at > since)

    return query.order_by(NetworkPolicy.created_at).all()

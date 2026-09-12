"""Schéma de données (SQLAlchemy)"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, ForeignKey, Index, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .time_utils import utcnow as _utcnow

# Table d'association Flow <-> AclProposal (many-to-many : plusieurs Flow peuvent être
# regroupés en une seule proposition ACL, cf. Phase B / regroupement).
flow_acl_proposal = Table(
    "flow_acl_proposal",
    Base.metadata,
    Column("flow_id", ForeignKey("flows.id", ondelete="CASCADE"), primary_key=True),
    Column("acl_proposal_id", ForeignKey("acl_proposals.id", ondelete="CASCADE"), primary_key=True, index=True),
)

# Sentinelles pour les contraintes d'unicité (NULL != NULL en SQL, donc deux lignes avec un
# champ NULL ne seraient jamais détectées comme doublons par une UniqueConstraint classique) --
# réutilisées par RuleRecommendation et AclProposal, jamais deux définitions qui pourraient
# diverger. Même solution que le UNSET_LABEL de Services/matrix_engine.py.
ZONE_UNSET = "(Non renseigné)"
RULE_NAME_UNSET = "(Aucune règle ciblée)"  # AclProposal.target_rule_name pour l'intent "create"


class LogEntry(Base):
    """Une ligne de log Cisco FTD, telle qu'ingérée. Représentation fidèle de la source."""

    __tablename__ = "log_entries"
    __table_args__ = (
        # ConnectionID seul (même combiné à DeviceUUID) N'EST PAS un identifiant stable dans
        # le temps : c'est un compteur borné par device, réutilisé au bout d'un moment (vu sur
        # données réelles : même ConnectionID, IP source différente, 14h d'écart -- deux
        # connexions distinctes, pas un doublon). FirstPacketSecond est nécessaire pour éviter
        # de traiter à tort deux connexions différentes comme un seul et même LogEntry.
        UniqueConstraint(
            "source", "device_uuid", "connection_id", "first_packet_at",
            name="uq_log_entry_source_device_connection_time",
        ),
        Index("ix_log_entries_src_dst", "src_ip", "dst_ip"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Provenance et conservation intégrale
    source: Mapped[Optional[str]] = mapped_column(index=True)
    raw_line: Mapped[str]
    firewall_device_ip: Mapped[Optional[str]]
    ingested_at: Mapped[datetime] = mapped_column(default=_utcnow)

    # Identifiants FTD
    device_uuid: Mapped[Optional[str]]
    connection_id: Mapped[Optional[int]]

    # Horodatage canonique = FirstPacketSecond (pas l'en-tête syslog, qui n'a pas d'année)
    first_packet_at: Mapped[Optional[datetime]] = mapped_column(index=True)

    # Lien vers le Flow consolidé, rempli par le Flow Engine (nullable avant traitement)
    flow_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flows.id", ondelete="SET NULL"), index=True)
    flow: Mapped[Optional["Flow"]] = relationship(back_populates="log_entries")

    # Décision et règle du firewall
    access_control_rule_action: Mapped[Optional[str]]
    access_control_rule_name: Mapped[Optional[str]]
    ac_policy: Mapped[Optional[str]]

    # Communication réseau
    src_ip: Mapped[Optional[str]]
    src_port: Mapped[Optional[int]]
    dst_ip: Mapped[Optional[str]]
    dst_port: Mapped[Optional[int]]
    protocol: Mapped[Optional[str]]
    ingress_zone: Mapped[Optional[str]]
    egress_zone: Mapped[Optional[str]]

    # Application applicative (AppID)
    application_protocol: Mapped[Optional[str]]
    web_application: Mapped[Optional[str]]

    # Volumétrie de cette connexion individuelle
    connection_duration: Mapped[Optional[int]]
    initiator_packets: Mapped[Optional[int]]
    responder_packets: Mapped[Optional[int]]
    initiator_bytes: Mapped[Optional[int]]
    responder_bytes: Mapped[Optional[int]]

    # Tous les champs restants du log brut (SSL*, DNS*, ICMP*, URL*, NAT_*, en-têtes...),
    # clé = nom original du champ Cisco FTD. Rien n'est perdu (cf. raw_line en plus).
    extra: Mapped[Optional[dict]] = mapped_column(JSON)


class Flow(Base):
    """Communication réseau consolidée : entité métier centrale, source de vérité pour
    la table plate des flux ET pour la matrice (vue dynamique construite par-dessus).
    """

    __tablename__ = "flows"
    __table_args__ = (
        UniqueConstraint("source", "src_ip", "dst_ip", "dst_port", "protocol", name="uq_flow_identity"),
        Index("ix_flows_src_dst", "src_ip", "dst_ip"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Clé d'identité de l'agrégation (pas de SrcPort : éphémère, voir docs/02)
    source: Mapped[Optional[str]] = mapped_column(index=True)
    src_ip: Mapped[str]
    dst_ip: Mapped[str]
    dst_port: Mapped[Optional[int]]
    protocol: Mapped[str]

    # Fenêtre d'observation
    first_seen_at: Mapped[Optional[datetime]]
    last_seen_at: Mapped[Optional[datetime]]

    # Agrégats (calculés et écrits par le Flow Engine)
    occurrence_count: Mapped[int] = mapped_column(default=0)
    allow_count: Mapped[int] = mapped_column(default=0)
    block_count: Mapped[int] = mapped_column(default=0)
    dominant_action: Mapped[Optional[str]]
    total_initiator_bytes: Mapped[int] = mapped_column(default=0)
    total_responder_bytes: Mapped[int] = mapped_column(default=0)
    total_connection_duration: Mapped[int] = mapped_column(default=0)

    # "Depuis la dernière clôture de cycle" (2026-09-06, demande de l'encadrant) -- même
    # agrégation que les 7 champs lifetime ci-dessus, incrémentée en parallèle par le Flow
    # Engine, mais RÉINITIALISÉE à chaque validation_cycle_engine.close_cycle() pour la
    # source de ce Flow. Corrige un bug réel : dominant_action (lifetime) ne redevient jamais
    # autre chose que "Mixed" une fois qu'une seule occurrence contradictoire a existé DANS
    # TOUTE L'HISTOIRE du flow, même des cycles plus tôt -- alors que le comportement du
    # cycle en cours peut être parfaitement tranché. Sert UNIQUEMENT au Cycle de validation
    # (diff + affichage "ce cycle") ; ne remplace jamais les champs lifetime ci-dessus, qui
    # gardent leur sens actuel ("depuis toujours", utilisés notamment par le Qualification
    # Engine pour son score de fréquence/action). Avant toute clôture pour la source de ce
    # Flow, ces champs valent exactement les mêmes valeurs que les champs lifetime (les deux
    # s'incrémentent ensemble depuis 0) -- aucune régression sur un tout premier cycle.
    cycle_occurrence_count: Mapped[int] = mapped_column(default=0)
    cycle_allow_count: Mapped[int] = mapped_column(default=0)
    cycle_block_count: Mapped[int] = mapped_column(default=0)
    cycle_dominant_action: Mapped[Optional[str]]
    cycle_total_initiator_bytes: Mapped[int] = mapped_column(default=0)
    cycle_total_responder_bytes: Mapped[int] = mapped_column(default=0)
    cycle_total_connection_duration: Mapped[int] = mapped_column(default=0)

    # Valeur dominante / dernière observée (recopiée depuis le LogEntry le plus récent)
    ingress_zone: Mapped[Optional[str]]
    egress_zone: Mapped[Optional[str]]
    application_protocol: Mapped[Optional[str]]
    web_application: Mapped[Optional[str]]
    last_access_control_rule_name: Mapped[Optional[str]]

    # Qualification (Qualification Engine) : explicable, jamais un score seul et opaque
    criticality_score: Mapped[Optional[float]]
    criticality_label: Mapped[Optional[str]] = mapped_column(index=True)
    security_status: Mapped[Optional[str]]
    qualification_reasons: Mapped[Optional[dict]] = mapped_column(JSON)

    # Validation humaine (Responsable Réseau) - un seul rôle de décision en V1
    validation_status: Mapped[str] = mapped_column(default="pending", index=True)
    validated_by: Mapped[Optional[str]]
    validated_at: Mapped[Optional[datetime]]

    # Décision CIBLE explicite sur l'action (2026-09-03, demande de l'encadrant) -- distincte
    # de dominant_action (observé dans les logs) ET de validation_status (triage pending/
    # approved/blocked, inchangé). Renseigné UNIQUEMENT quand le Responsable Réseau inverse
    # manuellement l'action observée (ex. bloquer un flux actuellement Allow) via le chemin
    # "inversion" de PATCH .../validation -- jamais par un Valider/Bloquer qui confirme
    # simplement ce qui est déjà observé. Reste actif (jamais écrasé par autre chose qu'une
    # nouvelle inversion) tant que le pare-feu ne s'aligne pas -- sert de référence au diff du
    # Cycle de validation suivant (recopié dans FlowSnapshot.decided_action à la clôture) pour
    # détecter une décision humaine toujours pas appliquée ("regle_non_appliquee"), distinct
    # d'une simple dérive organique du trafic ("modifie"). Voir docs/13-cycle-de-validation.md.
    decided_action: Mapped[Optional[str]]  # "Allow" | "Block" | None

    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    log_entries: Mapped[list["LogEntry"]] = relationship(back_populates="flow")
    acl_proposals: Mapped[list["AclProposal"]] = relationship(
        secondary=flow_acl_proposal, back_populates="flows"
    )
    # passive_deletes=True : laisse le ON DELETE CASCADE de la base gérer la suppression --
    # sans ça, SQLAlchemy tente par défaut un UPDATE ... SET flow_id = NULL avant le DELETE,
    # ce qui viole la contrainte NOT NULL de flow_id (bug rencontré et corrigé ici même).
    validation_history: Mapped[list["FlowValidationHistory"]] = relationship(
        back_populates="flow", order_by="FlowValidationHistory.created_at", passive_deletes=True
    )


class AclProposal(Base):
    """Proposition de règle ACL générée par l'ACL Engine, jamais appliquée automatiquement --
    toujours soumise à validation humaine. Quatre intents, trois générés automatiquement par
    une décision humaine déjà prise ailleurs (jamais une génération spéculative), un ajouté
    directement à la main :
      - "create"  : un Flow approuvé (`validation_status="approved"`) encore couvert
                    uniquement par "Default Action" (aucune règle explicite) -- formalise un
                    accès jusque-là géré par le comportement par défaut du firewall.
      - "tighten" : une RuleRecommendation "trop_permissive" acquittée -- propose de resserrer
                    une règle existante (`target_rule_name`).
      - "revoke"  : une RuleRecommendation "obsolete" acquittée -- propose de retirer une
                    règle existante (`target_rule_name`).
      - "manual"  : ajoutée directement par le Responsable Réseau (`POST /api/acl-proposals`),
                    pour un flux/équipement pas encore observé dans les logs -- exigence
                    actée dès la conception initiale de l'ACL Engine (2026-08-13), pas
                    seulement une génération à partir de données déjà présentes.
    Champs structurés (zone/objet réseau/port/protocole/action) plutôt qu'un texte au format
    ASA `access-list` : un FTD géré par FMC n'accepte pas cette syntaxe pour ses règles de
    trafic (clarifié le 2026-08-13, cf. docs/01-journal-technique.md) -- la vraie fiche à
    ressaisir dans FMC est structurée, `proposed_rule_text` n'en est qu'un résumé lisible
    généré à partir de ces champs, jamais la source de vérité.
    """

    __tablename__ = "acl_proposals"
    __table_args__ = (
        UniqueConstraint(
            "source", "intent", "ingress_zone", "egress_zone", "protocol", "dst_port", "target_rule_name",
            name="uq_acl_proposal_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Jamais deux `source` mélangées dans une même proposition (principe déjà acté).
    source: Mapped[Optional[str]]
    intent: Mapped[str] = mapped_column(index=True)  # "create" | "tighten" | "revoke" | "manual"

    # --- Fiche structurée -- ZONE_UNSET/RULE_NAME_UNSET (mêmes sentinelles que RuleRecommendation,
    # cf. docs/09) quand un champ n'est pas pertinent pour l'intent (ex. zones pour "revoke").
    ingress_zone: Mapped[str] = mapped_column(default=ZONE_UNSET)
    egress_zone: Mapped[str] = mapped_column(default=ZONE_UNSET)
    protocol: Mapped[Optional[str]]
    dst_port: Mapped[Optional[int]]
    src_networks: Mapped[Optional[dict]] = mapped_column(JSON)  # {"observed": [...], "count": n, "truncated": bool}
    dst_networks: Mapped[Optional[dict]] = mapped_column(JSON)
    proposed_action: Mapped[Optional[str]]  # "Allow" (create/tighten) | "Remove" (revoke)
    suggested_rule_name: Mapped[Optional[str]]  # généré, à ajuster par l'équipe réseau

    # Règle ACL existante concernée -- uniquement "tighten"/"revoke" (RULE_NAME_UNSET pour "create").
    target_rule_name: Mapped[str] = mapped_column(default=RULE_NAME_UNSET)

    # Traçabilité de la décision d'origine (nullable : "create" peut ne pas avoir de finding lié).
    source_recommendation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rule_recommendations.id"))

    proposed_rule_text: Mapped[Optional[str]]  # fiche lisible générée depuis les champs ci-dessus
    rationale: Mapped[Optional[dict]] = mapped_column(JSON)  # jamais un score seul opaque

    status: Mapped[str] = mapped_column(default="pending", index=True)  # pending / approved / rejected
    validated_by: Mapped[Optional[str]]
    validated_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    flows: Mapped[list["Flow"]] = relationship(secondary=flow_acl_proposal, back_populates="acl_proposals")
    # passive_deletes=True : même raison que Flow.validation_history ci-dessus.
    history: Mapped[list["AclProposalHistory"]] = relationship(
        back_populates="proposal", order_by="AclProposalHistory.created_at", passive_deletes=True
    )


class AclProposalHistory(Base):
    """Trace chaque changement de `AclProposal.status` : qui, quand, ancien -> nouveau statut --
    exigence actée dès la conception initiale de l'ACL Engine (même principe que
    FlowValidationHistory pour les Flow, cf. `08-historique-des-validations.md`), pas une
    décision reportée comme pour RuleRecommendation. Que la proposition soit générée
    automatiquement (`intent` = create/tighten/revoke) ou ajoutée à la main (`intent` =
    manual), la revue humaine qui en change le statut est tracée de la même façon -- l'origine
    de la proposition reste visible via `AclProposal.intent`, pas dupliquée ici. Écrite
    automatiquement par `app/acl_proposal_review.py` à chaque revue, jamais modifiée par
    ailleurs (table d'audit en ajout seul).
    """

    __tablename__ = "acl_proposal_history"

    id: Mapped[int] = mapped_column(primary_key=True)

    acl_proposal_id: Mapped[int] = mapped_column(ForeignKey("acl_proposals.id", ondelete="CASCADE"), index=True)
    proposal: Mapped["AclProposal"] = relationship(back_populates="history")

    old_status: Mapped[Optional[str]]
    new_status: Mapped[str]
    changed_by: Mapped[Optional[str]]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class FlowValidationHistory(Base):
    """Trace chaque changement de `Flow.validation_status` : qui, quand, ancien -> nouveau
    statut. Demande explicite de l'encadrant dès la conception initiale (traçabilité des
    décisions de sécurité) -- Flow ne garde que l'état courant, cette table garde l'historique
    complet. Écrite automatiquement par app/flow_validation.py à chaque validation, jamais
    modifiée par ailleurs (table d'audit en ajout seul).
    """

    __tablename__ = "flow_validation_history"

    id: Mapped[int] = mapped_column(primary_key=True)

    # CASCADE (pas SET NULL comme LogEntry) : cette table est un historique *du* Flow, elle
    # n'a pas de sens sans lui -- à la différence de LogEntry qui doit survivre indépendamment
    # (conservation intégrale des logs bruts). Aucune fonctionnalité de suppression de Flow
    # n'existe aujourd'hui ; ce choix ne s'applique donc encore à aucun cas réel.
    flow_id: Mapped[int] = mapped_column(ForeignKey("flows.id", ondelete="CASCADE"), index=True)
    flow: Mapped["Flow"] = relationship(back_populates="validation_history")

    old_status: Mapped[Optional[str]]
    new_status: Mapped[str]
    validated_by: Mapped[Optional[str]]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    # Renseignés UNIQUEMENT sur le chemin "inversion d'action" (2026-09-03) -- None sur un
    # Valider/Bloquer classique qui ne fait que confirmer l'action déjà observée. Figent ce
    # qui était vrai à l'instant de LA décision (jamais relus depuis Flow, qui continue
    # d'évoluer) : nécessaire pour que la fiche PDF générée plus tard depuis cette ligne
    # reste fidèle à ce qui a été décidé, même si le Flow a changé entretemps.
    justification: Mapped[Optional[str]]
    observed_action_before: Mapped[Optional[str]]  # dominant_action au moment de la décision
    decided_action: Mapped[Optional[str]]  # "Allow" | "Block" -- la cible décidée


class ValidationCycle(Base):
    """Clôture d'un cycle de validation périodique : fige l'état de tous les Flow d'**une
    source** (un cycle = un firewall/site, jamais plusieurs mélangés) pour servir de
    référence ("Matrice Validée") au cycle suivant de cette même source. Demande directe de
    l'encadrant (2026-08-19) : comparer la Matrice Réelle (l'état courant, déjà dynamique --
    Matrix/Flows Engine) à la dernière baseline validée, pour ne faire revoir au Responsable
    Réseau que ce qui a changé depuis. Jamais purgé -- même principe que
    FlowValidationHistory/AclProposalHistory, chaque cycle clôturé reste en base
    indéfiniment pour l'audit.

    Révisé le 2026-08-21 (retour de l'encadrant après démo) : un cycle était initialement
    global (toutes sources confondues, `source` nullable, cf. git blame) -- corrigé en
    scope obligatoire par source, cohérent avec le workflow réel ("j'importe UN log" = une
    source précise, pas le parc entier). Voir docs/13-cycle-de-validation.md.
    """

    __tablename__ = "validation_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(index=True)
    closed_by: Mapped[Optional[str]]
    closed_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)
    flow_count: Mapped[int] = mapped_column(default=0)
    note: Mapped[Optional[str]]

    entries: Mapped[list["FlowSnapshot"]] = relationship(back_populates="cycle", passive_deletes=True)


class FlowSnapshot(Base):
    """État figé d'un Flow au moment de la clôture d'un ValidationCycle -- sert à la fois de
    référence pour détecter les écarts (nouveau/disparu/modifié) au cycle suivant, ET de
    source pour reconstruire la "Matrice Validée" comme une vraie matrice consultable à part
    entière (pas seulement un diff -- demande explicite de Loulou, 2026-08-21, après
    confusion sur "où est la Matrice Validée ?"). Ne duplique jamais les champs d'identité
    d'un Flow (source/src_ip/dst_ip/dst_port/protocol) : la contrainte d'unicité
    `uq_flow_identity` garantit qu'ils ne changent jamais pour un flow_id donné une fois créé
    -- seuls les champs qui PEUVENT évoluer entre deux imports/qualifications sont figés ici.
    Voir Services/validation_cycle_engine.py pour la logique de comparaison et de
    reconstruction de matrice.
    """

    __tablename__ = "flow_snapshots"
    __table_args__ = (
        UniqueConstraint("cycle_id", "flow_id", name="uq_flow_snapshot_cycle_flow"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    cycle_id: Mapped[int] = mapped_column(ForeignKey("validation_cycles.id", ondelete="CASCADE"), index=True)
    cycle: Mapped["ValidationCycle"] = relationship(back_populates="entries")

    # SET NULL (pas CASCADE comme FlowValidationHistory) : un cycle clôturé reste un
    # document d'audit à part entière, même dans l'hypothèse -- aujourd'hui impossible,
    # cf. règle "Flow jamais supprimé" -- où un Flow viendrait à disparaître techniquement.
    flow_id: Mapped[Optional[int]] = mapped_column(ForeignKey("flows.id", ondelete="SET NULL"), index=True)

    # État figé au moment T -- suffisant pour calculer un diff sans retourner aux LogEntry
    # ni recalculer quoi que ce soit (cohérent avec le principe "jamais un score/statut
    # recalculé implicitement à partir d'autre chose que sa propre trace").
    occurrence_count: Mapped[int]
    allow_count: Mapped[int]
    block_count: Mapped[int]
    dominant_action: Mapped[Optional[str]]
    last_seen_at: Mapped[Optional[datetime]]
    ingress_zone: Mapped[Optional[str]]
    egress_zone: Mapped[Optional[str]]
    last_access_control_rule_name: Mapped[Optional[str]]
    criticality_label: Mapped[Optional[str]]
    validation_status: Mapped[str]
    # Ajoutés le 2026-08-21 pour que la Matrice Validée supporte les mêmes modes de
    # coloration que la Matrice Réelle (volume de données, débit) -- pas nécessaires au
    # diff (jamais dans STRUCTURAL_FIELDS), uniquement pour reconstruire une matrice fidèle.
    total_initiator_bytes: Mapped[int] = mapped_column(default=0)
    total_responder_bytes: Mapped[int] = mapped_column(default=0)
    total_connection_duration: Mapped[int] = mapped_column(default=0)
    application_protocol: Mapped[Optional[str]]
    # Ajouté le 2026-09-03 : décision cible explicite (Flow.decided_action) figée à la
    # clôture -- permet au diff du cycle SUIVANT de distinguer "personne n'a rien décidé,
    # le trafic a juste changé" (modifie) de "une décision existait et le pare-feu ne s'y
    # conforme toujours pas" (regle_non_appliquee), cf. Services/validation_cycle_engine.py.
    decided_action: Mapped[Optional[str]]

    # Ajoutés le 2026-09-06 : tally Flow.cycle_* du cycle qui vient de se clôturer (avant sa
    # remise à zéro sur Flow) -- remplace dominant_action (lifetime, contaminable pour
    # toujours par une seule occurrence contradictoire ancienne) dans la comparaison du
    # diff. cycle_allow_count/cycle_block_count permettent aussi d'afficher une répartition
    # chiffrée ("18 Allow / 2 Block") côté "avant" quand cycle_dominant_action valait "Mixed",
    # jamais le mot brut. Voir Services/validation_cycle_engine.py.
    cycle_occurrence_count: Mapped[int] = mapped_column(default=0)
    cycle_allow_count: Mapped[int] = mapped_column(default=0)
    cycle_block_count: Mapped[int] = mapped_column(default=0)
    cycle_dominant_action: Mapped[Optional[str]]
    cycle_total_initiator_bytes: Mapped[int] = mapped_column(default=0)
    cycle_total_responder_bytes: Mapped[int] = mapped_column(default=0)
    cycle_total_connection_duration: Mapped[int] = mapped_column(default=0)


class RuleRecommendation(Base):
    """Finding produit par le Recommendation Engine sur une règle ACL déjà appliquée par
    le firewall (jamais une proposition de nouvelle règle -- ça, c'est le rôle de l'ACL
    Engine, pas encore commencé). Persisté (contrairement à la Matrice, vue dynamique pure)
    car chaque finding porte un état de revue humaine qui doit survivre aux ré-exécutions
    du moteur après un nouvel import. Les Flow concernés ne sont jamais stockés en double ici
    : recalculés à la demande via (source, rule_name) ou (source, ingress_zone, egress_zone).
    """

    __tablename__ = "rule_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "source", "finding_type", "rule_name", "ingress_zone", "egress_zone",
            name="uq_rule_recommendation_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Jamais mélanger deux `source` dans un même finding (même principe que AclProposal).
    source: Mapped[Optional[str]] = mapped_column(index=True)

    # "obsolete" | "trop_permissive" | "sans_regle_explicite"
    finding_type: Mapped[str] = mapped_column(index=True)

    # Toujours une valeur réelle et non vide : le nom de règle ACL observé (ex.
    # "ACL_ANY_INTERNET_HTTPS_OUT"), ou le littéral "Default Action" tel qu'observé dans les
    # logs pour "sans_regle_explicite" -- jamais un synthétique inventé par le moteur.
    # ingress_zone/egress_zone = ZONE_UNSET sauf pour "sans_regle_explicite", où ils portent
    # le vrai regroupement (pas de rule_name distinctif à regrouper dans ce cas).
    rule_name: Mapped[str]
    ingress_zone: Mapped[str] = mapped_column(default=ZONE_UNSET)
    egress_zone: Mapped[str] = mapped_column(default=ZONE_UNSET)

    flow_count: Mapped[int] = mapped_column(default=0)

    # Preuve explicite du finding (jamais un score seul opaque, même principe que
    # Flow.qualification_reasons) : métriques exactes ayant déclenché la détection.
    evidence: Mapped[Optional[dict]] = mapped_column(JSON)

    # pending / acknowledged / dismissed -- revue humaine, jamais automatique.
    status: Mapped[str] = mapped_column(default="pending", index=True)
    reviewed_by: Mapped[Optional[str]]
    reviewed_at: Mapped[Optional[datetime]]

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class RuleEnforcementClaim(Base):
    """Suivi léger d'une "réclamation" sur un flux "Règle non appliquée" (2026-09-10, demande
    de l'encadrant) -- une décision explicite (`Flow.decided_action`) existe mais l'action
    réellement observée ne s'y conforme toujours pas. Une ligne par Flow (jamais plusieurs
    décisions actives en même temps sur un Flow, cf. `Flow.decided_action`) :

    - `first_detected_at` posé AUTOMATIQUEMENT par le calcul du diff
      (`Services/validation_cycle_engine.py::compute_diff`), la toute première fois que ce
      Flow est vu "regle_non_appliquee" -- indépendamment de toute action humaine (décision de
      conception actée le 2026-09-10 : sinon "première détection" et "première réclamation"
      seraient toujours la même date, perdant tout leur sens l'une par rapport à l'autre).
    - `last_claimed_at`/`claim_count` uniquement mis à jour par un clic explicite "Déclarer la
      réclamation" (app/rule_enforcement_claims.py), jamais automatiquement.

    Supprimée (jamais laissée obsolète) dès qu'une NOUVELLE décision remplace l'ancienne via
    "Changer la règle" -- portait sur une cible qui n'existe plus, cf.
    flow_validation.py::apply_rule_change.
    """

    __tablename__ = "rule_enforcement_claims"

    id: Mapped[int] = mapped_column(primary_key=True)

    # CASCADE (pas SET NULL) : cette table est un suivi *du* Flow, elle n'a pas de sens sans
    # lui -- même raisonnement que FlowValidationHistory. unique=True : une seule réclamation
    # active par Flow, jamais deux lignes concurrentes pour la même décision.
    flow_id: Mapped[int] = mapped_column(ForeignKey("flows.id", ondelete="CASCADE"), unique=True, index=True)
    flow: Mapped["Flow"] = relationship()

    first_detected_at: Mapped[datetime] = mapped_column(default=_utcnow)
    last_claimed_at: Mapped[Optional[datetime]]
    claim_count: Mapped[int] = mapped_column(default=0)


class NetworkPolicy(Base):
    """Politique de sous-réseau (2026-09-10, demande de l'encadrant) -- fonctionnalité NOUVELLE
    et VOLONTAIREMENT ISOLÉE : aucun lien avec Flow.decided_action, le diff de cycle
    (Services/validation_cycle_engine.py), ou FlowSnapshot. Un simple enregistrement à la main
    d'une décision sur un REGROUPEMENT d'IP (jamais un Flow individuel) -- le CIDR source est du
    texte libre, jamais validé ni contraint : peut venir d'une suggestion de regroupement
    (Services/subnet_observation.py, elle-même purement indicative -- le système ne peut pas
    connaître le vrai découpage réseau de Nouvelair à partir des seules IP des logs) ou être
    saisi librement. `destination` est également du texte libre (zone, IP, ou CIDR). AUCUNE
    logique de correspondance ni d'application automatique aux Flow pour l'instant -- juste une
    fiche enregistrée, comme le sont déjà les fiches de changement de règle et de non-
    application (app/fiche_pdf.py), mais sans aucun rattachement à un flow_id précis.
    """

    __tablename__ = "network_policies"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Contexte (quelle source/firewall a inspiré cette politique) -- jamais une contrainte,
    # une politique peut très bien ne pas être rattachée à une source précise.
    source: Mapped[Optional[str]] = mapped_column(index=True)
    src_cidr: Mapped[str]
    destination: Mapped[str]
    protocol: Mapped[Optional[str]]
    dst_port: Mapped[Optional[int]]
    action: Mapped[str]  # "Allow" | "Block"
    justification: Mapped[str]
    decided_by: Mapped[Optional[str]]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ImportLog(Base):
    """Historique des imports de logs (2026-09-11, demande de l'encadrant) -- table d'AUDIT EN
    AJOUT SEUL, jamais modifiée après coup, même principe que FlowValidationHistory. PAS de FK
    (contrairement à FlowValidationHistory, qui trace un Flow précis) : un import n'a pas
    d'entité parente unique à référencer, c'est son propre enregistrement autonome. Écrite
    automatiquement par app/import_log.py::record_import() à la fin de chaque import réussi
    (appelée depuis main.py::import_logs(), PAS depuis app/ingestion.py -- ce module reste
    intégralement inchangé, ce n'est qu'un enregistrement du résultat déjà calculé par
    ingestion.import_log_file(), aucune nouvelle logique d'import). Consultable même après avoir
    quitté puis rechargé la page Import (frontend/src/pages/ImportPage.tsx).
    """

    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    filename: Mapped[str]
    # ingestion.import_log_file() retourne `sources: list[str]` (un fichier peut en théorie
    # contenir plusieurs ACPolicy) -- concaténées ici en une seule chaîne lisible ("SITE-A,
    # SITE-B" dans ce cas rare) plutôt qu'une deuxième table, un fichier normal ne donnant
    # qu'une seule source.
    source: Mapped[str] = mapped_column(index=True)
    imported_at: Mapped[datetime] = mapped_column(default=_utcnow, index=True)

    lines_read: Mapped[int]
    log_entries_created: Mapped[int]
    log_entries_skipped_duplicate: Mapped[int]
    parsing_errors: Mapped[int]
    flows_touched: Mapped[int]

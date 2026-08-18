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

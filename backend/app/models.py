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
    """Proposition de règle ACL générée par l'ACL Engine à partir d'un ou plusieurs Flow
    validés. Ne modifie jamais le firewall : une proposition reste soumise à validation
    humaine avant toute intégration manuelle.
    """

    __tablename__ = "acl_proposals"
    __table_args__ = (Index("ix_acl_proposals_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    # Contexte : dénormalisé pour filtrage, mais la vraie source de vérité reste les Flow liés.
    # L'ACL Engine ne doit jamais regrouper des Flow de `source` différentes dans une même
    # proposition (cf. principe "aucune fusion silencieuse de sources").
    source: Mapped[Optional[str]]

    proposed_action: Mapped[Optional[str]]
    proposed_rule_text: Mapped[Optional[str]]
    rationale: Mapped[Optional[dict]] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(default="pending")
    validated_by: Mapped[Optional[str]]
    validated_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    flows: Mapped[list["Flow"]] = relationship(secondary=flow_acl_proposal, back_populates="acl_proposals")


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

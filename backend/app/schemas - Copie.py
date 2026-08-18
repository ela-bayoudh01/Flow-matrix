"""Schémas Pydantic (I/O API)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ImportSummary(BaseModel):
    filename: str
    lines_read: int
    log_entries_created: int
    log_entries_skipped_duplicate: int
    parsing_errors: int
    flows_touched: int


class QualificationRunSummary(BaseModel):
    """Résumé retourné après une exécution du Qualification Engine (POST /api/flows/qualify)."""

    total_qualified: int
    label_counts: dict[str, int]


class FlowOut(BaseModel):
    """Un Flow tel qu'affiché dans la table plate ou le détail d'une cellule de matrice --
    tous les champs demandés pour le panneau de détail (voir docs/00, décision 2026-08-11).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Optional[str]
    src_ip: str
    dst_ip: str
    dst_port: Optional[int]
    protocol: str
    dominant_action: Optional[str]
    occurrence_count: int
    total_initiator_bytes: int
    total_responder_bytes: int
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    ingress_zone: Optional[str]
    egress_zone: Optional[str]
    application_protocol: Optional[str]
    web_application: Optional[str]
    last_access_control_rule_name: Optional[str]
    criticality_score: Optional[float]
    criticality_label: Optional[str]
    security_status: Optional[str]
    validation_status: str
    validated_by: Optional[str]
    validated_at: Optional[datetime]


class FlowsSummary(BaseModel):
    """Résumé agrégé (mêmes filtres que la liste) -- affiché en haut du panneau de détail
    d'une cellule ou de la table plate."""

    total_flows: int
    allow_count: int
    block_count: int
    criticality_breakdown: dict[str, int]


class FlowsResponse(BaseModel):
    items: list[FlowOut]
    total_count: int
    summary: FlowsSummary


class MatrixCell(BaseModel):
    row: Optional[str]
    col: Optional[str]
    flow_count: int
    allow_count: int
    block_count: int
    total_bytes: int
    total_duration_seconds: int
    criticality_breakdown: dict[str, int]


class MatrixResponse(BaseModel):
    dimension: str
    cells: list[MatrixCell]
    dimension_notice: Optional[str] = None


class ValidationUpdate(BaseModel):
    status: str  # "approved" ou "blocked" -- voir main.py VALID_VALIDATION_STATUSES
    validated_by: Optional[str] = None


class ValidationHistoryOut(BaseModel):
    """Une entrée de FlowValidationHistory, avec le contexte du Flow concerné inclus."""

    id: int
    flow_id: int
    source: Optional[str]
    src_ip: str
    dst_ip: str
    dst_port: Optional[int]
    protocol: str
    old_status: Optional[str]
    new_status: str
    validated_by: Optional[str]
    created_at: datetime


class ValidationHistoryResponse(BaseModel):
    items: list[ValidationHistoryOut]
    total_count: int


class RecommendationRunSummary(BaseModel):
    """Résumé retourné après une exécution du Recommendation Engine (POST /api/recommendations/run)."""

    total_findings: int
    findings_by_type: dict[str, int]
    created: int
    updated: int
    observation_window_days: Optional[float]
    obsolete_detection_enabled: bool


class RuleRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Optional[str]
    finding_type: str
    rule_name: str
    ingress_zone: str
    egress_zone: str
    flow_count: int
    evidence: Optional[dict]
    status: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class RuleRecommendationsResponse(BaseModel):
    items: list[RuleRecommendationOut]
    total_count: int


class RecommendationReview(BaseModel):
    status: str  # "acknowledged" ou "dismissed" -- voir main.py VALID_RECOMMENDATION_STATUSES
    reviewed_by: Optional[str] = None


class AclProposalRunSummary(BaseModel):
    """Résumé retourné après une exécution de l'ACL Engine (POST /api/acl-proposals/run)."""

    total_proposals: int
    created: int
    updated: int
    by_intent: dict[str, int]


class AclProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Optional[str]
    intent: str
    ingress_zone: str
    egress_zone: str
    protocol: Optional[str]
    dst_port: Optional[int]
    src_networks: Optional[dict]
    dst_networks: Optional[dict]
    proposed_action: Optional[str]
    suggested_rule_name: Optional[str]
    target_rule_name: str
    source_recommendation_id: Optional[int]
    proposed_rule_text: Optional[str]
    rationale: Optional[dict]
    status: str
    validated_by: Optional[str]
    validated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class AclProposalsResponse(BaseModel):
    items: list[AclProposalOut]
    total_count: int


class AclProposalReview(BaseModel):
    status: str  # "approved" ou "rejected" -- voir main.py VALID_ACL_PROPOSAL_STATUSES
    validated_by: Optional[str] = None


class AclProposalManualCreate(BaseModel):
    """Ajout manuel d'une proposition, pour un flux/équipement pas encore observé dans les
    logs -- exigence actée dès la conception initiale de l'ACL Engine. `justification` est
    obligatoire : sans Flow ni RuleRecommendation d'origine, c'est la seule preuve disponible.
    """

    source: Optional[str] = None
    ingress_zone: Optional[str] = None
    egress_zone: Optional[str] = None
    protocol: Optional[str] = None
    dst_port: Optional[int] = None
    src_networks: list[str] = []
    dst_networks: list[str] = []
    proposed_action: str
    suggested_rule_name: Optional[str] = None
    target_rule_name: Optional[str] = None
    justification: str
    created_by: Optional[str] = None


class AclProposalHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    acl_proposal_id: int
    old_status: Optional[str]
    new_status: str
    changed_by: Optional[str]
    created_at: datetime


class AclProposalHistoryResponse(BaseModel):
    items: list[AclProposalHistoryOut]
    total_count: int

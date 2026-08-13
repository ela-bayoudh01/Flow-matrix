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
    criticality_breakdown: dict[str, int]


class MatrixResponse(BaseModel):
    dimension: str
    cells: list[MatrixCell]


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

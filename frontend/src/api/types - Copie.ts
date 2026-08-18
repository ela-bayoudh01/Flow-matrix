// Types miroir des schémas Pydantic du backend (backend/app/schemas.py).
// Garder synchronisé manuellement -- pas de génération automatique en V1.

export interface FlowOut {
  id: number;
  source: string | null;
  src_ip: string;
  dst_ip: string;
  dst_port: number | null;
  protocol: string;
  dominant_action: string | null;
  occurrence_count: number;
  total_initiator_bytes: number;
  total_responder_bytes: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  ingress_zone: string | null;
  egress_zone: string | null;
  application_protocol: string | null;
  web_application: string | null;
  last_access_control_rule_name: string | null;
  criticality_score: number | null;
  criticality_label: string | null;
  security_status: string | null;
  validation_status: string;
  validated_by: string | null;
  validated_at: string | null;
}

export interface FlowsSummary {
  total_flows: number;
  allow_count: number;
  block_count: number;
  criticality_breakdown: Record<string, number>;
}

export interface FlowsResponse {
  items: FlowOut[];
  total_count: number;
  summary: FlowsSummary;
}

// Filtres communs à GET /api/flows et GET /api/matrix (backend/app/flow_filters.py --
// une seule définition partagée côté backend, on reflète la même liste ici).
export interface FlowFilterValues {
  source?: string;
  ingress_zone?: string;
  egress_zone?: string;
  src_ip?: string;
  dst_ip?: string;
  protocol?: string;
  dst_port?: number;
  dominant_action?: string;
  validation_status?: string;
  criticality_label?: string;
  application_protocol?: string;
  web_application?: string;
}

export interface FlowsFilters extends FlowFilterValues {
  limit?: number;
  offset?: number;
  // Drill-down d'une cellule de matrice, pour n'importe quelle dimension (pas seulement
  // "zone" -- ingress_zone/egress_zone ci-dessus restent utilisables séparément comme
  // filtre "normal", indépendamment d'un drill-down de cellule). Les trois vont ensemble.
  dimension?: string;
  row_value?: string;
  col_value?: string;
}

export interface MatrixCell {
  row: string | null;
  col: string | null;
  flow_count: number;
  allow_count: number;
  block_count: number;
  total_bytes: number;
  total_duration_seconds: number;
  criticality_breakdown: Record<string, number>;
}

export interface MatrixResponse {
  dimension: string;
  cells: MatrixCell[];
  dimension_notice: string | null;
}

export interface ValidationUpdate {
  status: "approved" | "blocked";
  validated_by?: string;
}

export interface ValidationHistoryOut {
  id: number;
  flow_id: number;
  source: string | null;
  src_ip: string;
  dst_ip: string;
  dst_port: number | null;
  protocol: string;
  old_status: string | null;
  new_status: string;
  validated_by: string | null;
  created_at: string;
}

export interface ValidationHistoryResponse {
  items: ValidationHistoryOut[];
  total_count: number;
}

// Miroir de RuleRecommendation (backend/app/models.py) -- findings du Recommendation Engine.
export interface RuleRecommendationOut {
  id: number;
  source: string | null;
  finding_type: "trop_permissive" | "obsolete" | "sans_regle_explicite";
  rule_name: string;
  ingress_zone: string;
  egress_zone: string;
  flow_count: number;
  evidence: Record<string, unknown> | null;
  status: "pending" | "acknowledged" | "dismissed";
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuleRecommendationsResponse {
  items: RuleRecommendationOut[];
  total_count: number;
}

export interface RecommendationFilters {
  status?: string;
  finding_type?: string;
  source?: string;
}

export interface QualificationRunSummary {
  total_qualified: number;
  label_counts: Record<string, number>;
}

export interface RecommendationRunSummary {
  total_findings: number;
  findings_by_type: Record<string, number>;
  created: number;
  updated: number;
  observation_window_days: number | null;
  obsolete_detection_enabled: boolean;
}

export interface RecommendationReview {
  status: "acknowledged" | "dismissed";
  reviewed_by?: string;
}

// Miroir de AclProposal (backend/app/models.py) -- propositions de l'ACL Engine.
export interface NetworkSummary {
  observed: string[];
  count: number;
  truncated: boolean;
}

export interface AclProposalOut {
  id: number;
  source: string | null;
  intent: "create" | "tighten" | "revoke" | "manual";
  ingress_zone: string;
  egress_zone: string;
  protocol: string | null;
  dst_port: number | null;
  src_networks: NetworkSummary | null;
  dst_networks: NetworkSummary | null;
  proposed_action: string | null;
  suggested_rule_name: string | null;
  target_rule_name: string;
  source_recommendation_id: number | null;
  proposed_rule_text: string | null;
  rationale: Record<string, unknown> | null;
  status: "pending" | "approved" | "rejected";
  validated_by: string | null;
  validated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AclProposalsResponse {
  items: AclProposalOut[];
  total_count: number;
}

export interface AclProposalFilters {
  status?: string;
  intent?: string;
  source?: string;
}

export interface AclProposalRunSummary {
  total_proposals: number;
  created: number;
  updated: number;
  by_intent: Record<string, number>;
}

export interface AclProposalReview {
  status: "approved" | "rejected";
  validated_by?: string;
}

export interface AclProposalManualCreate {
  source?: string;
  ingress_zone?: string;
  egress_zone?: string;
  protocol?: string;
  dst_port?: number;
  src_networks: string[];
  dst_networks: string[];
  proposed_action: string;
  suggested_rule_name?: string;
  target_rule_name?: string;
  justification: string;
  created_by?: string;
}

export interface AclProposalHistoryOut {
  id: number;
  acl_proposal_id: number;
  old_status: string | null;
  new_status: string;
  changed_by: string | null;
  created_at: string;
}

export interface AclProposalHistoryResponse {
  items: AclProposalHistoryOut[];
  total_count: number;
}

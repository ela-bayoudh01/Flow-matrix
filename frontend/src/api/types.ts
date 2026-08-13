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
}

export interface MatrixCell {
  row: string | null;
  col: string | null;
  flow_count: number;
  allow_count: number;
  block_count: number;
  total_bytes: number;
  criticality_breakdown: Record<string, number>;
}

export interface MatrixResponse {
  dimension: string;
  cells: MatrixCell[];
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

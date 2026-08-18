// Client HTTP minimal -- pas de librairie externe, juste fetch + gestion d'erreur commune.
// L'URL de base est configurable via VITE_API_BASE_URL (voir .env), par défaut l'API locale.

import type {
  FlowFilterValues,
  FlowsFilters,
  FlowsResponse,
  MatrixResponse,
  FlowOut,
  ValidationUpdate,
  ValidationHistoryResponse,
  QualificationRunSummary,
  RecommendationFilters,
  RecommendationRunSummary,
  RecommendationReview,
  RuleRecommendationOut,
  RuleRecommendationsResponse,
  AclProposalFilters,
  AclProposalHistoryResponse,
  AclProposalManualCreate,
  AclProposalOut,
  AclProposalReview,
  AclProposalRunSummary,
  AclProposalsResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body || response.statusText);
  }
  return response.json() as Promise<T>;
}

function buildQuery(params: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params) as [string, unknown][]) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  }
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  getFlows(filters: FlowsFilters = {}): Promise<FlowsResponse> {
    return request(`/api/flows${buildQuery(filters)}`);
  },

  getMatrix(dimension = "zone", filters: FlowFilterValues = {}): Promise<MatrixResponse> {
    return request(`/api/matrix${buildQuery({ dimension, ...filters })}`);
  },

  validateFlow(flowId: number, payload: ValidationUpdate): Promise<FlowOut> {
    return request(`/api/flows/${flowId}/validation`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  getValidationHistory(params: { flowId?: number; limit?: number } = {}): Promise<ValidationHistoryResponse> {
    return request(`/api/validation-history${buildQuery({ flow_id: params.flowId, limit: params.limit })}`);
  },

  qualifyFlows(source?: string): Promise<QualificationRunSummary> {
    return request(`/api/flows/qualify${buildQuery({ source })}`, { method: "POST" });
  },

  getRecommendations(filters: RecommendationFilters = {}): Promise<RuleRecommendationsResponse> {
    return request(`/api/recommendations${buildQuery(filters)}`);
  },

  runRecommendations(source?: string): Promise<RecommendationRunSummary> {
    return request(`/api/recommendations/run${buildQuery({ source })}`, { method: "POST" });
  },

  reviewRecommendation(id: number, payload: RecommendationReview): Promise<RuleRecommendationOut> {
    return request(`/api/recommendations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  getAclProposals(filters: AclProposalFilters = {}): Promise<AclProposalsResponse> {
    return request(`/api/acl-proposals${buildQuery(filters)}`);
  },

  runAclProposals(source?: string): Promise<AclProposalRunSummary> {
    return request(`/api/acl-proposals/run${buildQuery({ source })}`, { method: "POST" });
  },

  reviewAclProposal(id: number, payload: AclProposalReview): Promise<AclProposalOut> {
    return request(`/api/acl-proposals/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  createManualAclProposal(payload: AclProposalManualCreate): Promise<AclProposalOut> {
    return request(`/api/acl-proposals`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getAclProposalHistory(params: { aclProposalId?: number; limit?: number } = {}): Promise<AclProposalHistoryResponse> {
    return request(`/api/acl-proposal-history${buildQuery({ acl_proposal_id: params.aclProposalId, limit: params.limit })}`);
  },
};

export { ApiError };

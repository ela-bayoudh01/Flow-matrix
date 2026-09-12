// Client HTTP minimal -- pas de librairie externe, juste fetch + gestion d'erreur commune.
// L'URL de base est configurable via VITE_API_BASE_URL (voir .env), par défaut l'API locale.

import type {
  ImportSummary,
  ImportLogsResponse,
  FlowFilterValues,
  FlowsFilters,
  FlowsResponse,
  MatrixResponse,
  FlowOut,
  LogEntriesResponse,
  ValidationUpdate,
  RuleChangeUpdate,
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
  CellDiffResponse,
  FlowDiffFilters,
  FlowDiffResponse,
  ValidatedMatrixResponse,
  ValidationCyclesResponse,
  ValidationCycleOut,
  RuleEnforcementClaimOut,
  SubnetObservationsResponse,
  SubnetDiffResponse,
  NetworkPolicyCreate,
  NetworkPolicyOut,
  NetworkPoliciesResponse,
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

// XHR plutôt que fetch : c'est le seul appel de l'app qui a besoin d'une vraie progression
// d'upload (`xhr.upload.onprogress`), fetch ne l'expose pas nativement. Le traitement
// serveur (parsing + Flow Engine) continue bien après la fin de l'upload -- cette
// progression ne couvre que la phase d'envoi, jamais présentée comme le progrès total
// (cf. ImportPage.tsx, deux phases distinctes affichées séparément).
function uploadLogFile(file: File, onUploadProgress?: (percent: number) => void): Promise<ImportSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/api/logs/import`);
    xhr.upload.onprogress = (event) => {
      if (onUploadProgress && event.lengthComputable) {
        onUploadProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as ImportSummary);
        } catch {
          reject(new ApiError(xhr.status, "Réponse invalide du serveur"));
        }
      } else {
        reject(new ApiError(xhr.status, xhr.responseText || xhr.statusText));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Erreur réseau pendant l'import"));
    const formData = new FormData();
    formData.append("file", file);
    xhr.send(formData);
  });
}

export const api = {
  importLogs: uploadLogFile,

  // Historique des imports (2026-09-11, demande de l'encadrant) -- lecture seule, toutes
  // sources confondues, triée du plus récent au plus ancien côté backend.
  getImportLogs(params: { limit?: number; offset?: number } = {}): Promise<ImportLogsResponse> {
    return request(`/api/import-logs${buildQuery(params)}`);
  },

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

  changeFlowRule(flowId: number, payload: RuleChangeUpdate): Promise<FlowOut> {
    return request(`/api/flows/${flowId}/change-rule`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  getValidationHistory(params: { flowId?: number; q?: string; limit?: number } = {}): Promise<ValidationHistoryResponse> {
    return request(`/api/validation-history${buildQuery({ flow_id: params.flowId, q: params.q, limit: params.limit })}`);
  },

  // Drill-down (2026-09-06, demande de l'encadrant) : connexions individuelles sous-jacentes
  // à un Flow -- occurrence_count agrège potentiellement des milliers de LogEntry.
  getFlowLogEntries(flowId: number, params: { limit?: number; offset?: number } = {}): Promise<LogEntriesResponse> {
    return request(`/api/flows/${flowId}/log-entries${buildQuery(params)}`);
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

  getValidationCycleDiff(filters: FlowDiffFilters = {}): Promise<FlowDiffResponse> {
    return request(`/api/validation-cycles/diff${buildQuery(filters)}`);
  },

  // Fusion "Politiques de sous-réseau" -> Cycle de validation (2026-09-11) -- même
  // regroupement suggestif que getObservedSubnets ci-dessous, avec la répartition des écarts
  // du cycle en plus. Voir Services/validation_cycle_engine.py::compute_subnet_diff.
  getValidationCycleSubnetDiff(source: string, prefixLength?: number): Promise<SubnetDiffResponse> {
    return request(`/api/validation-cycles/subnet-diff${buildQuery({ source, prefix_length: prefixLength })}`);
  },

  getValidationCycleCellDiff(dimension = "zone", filters: FlowFilterValues = {}): Promise<CellDiffResponse> {
    return request(`/api/validation-cycles/cell-diff${buildQuery({ dimension, ...filters })}`);
  },

  closeValidationCycle(params: { source: string; closedBy?: string; note?: string }): Promise<ValidationCycleOut> {
    return request(
      `/api/validation-cycles/close${buildQuery({ source: params.source, closed_by: params.closedBy, note: params.note })}`,
      { method: "POST" },
    );
  },

  getValidationCycles(params: { source?: string; limit?: number } = {}): Promise<ValidationCyclesResponse> {
    return request(`/api/validation-cycles${buildQuery({ source: params.source, limit: params.limit })}`);
  },

  // Rapport de clôture de cycle (2026-09-10) -- URL directe pour un <a href download>, jamais
  // un fetch : régénéré à la demande, toujours retéléchargeable depuis l'historique des cycles.
  cycleReportUrl(cycleId: number): string {
    return `${API_BASE_URL}/api/validation-cycles/${cycleId}/report.pdf`;
  },

  runAclProposalsForCycle(cycleId: number): Promise<AclProposalRunSummary> {
    return request(`/api/acl-proposals/run${buildQuery({ cycle_id: cycleId })}`, { method: "POST" });
  },

  getValidatedMatrix(source: string, dimension = "zone"): Promise<ValidatedMatrixResponse> {
    return request(`/api/validation-cycles/matrix${buildQuery({ source, dimension })}`);
  },

  // Drill-down d'une cellule de la Matrice Validée (2026-09-09, demande de l'encadrant) --
  // lit FlowSnapshot (l'état figé de ce cycle précis), jamais Flow en direct.
  getValidatedMatrixFlows(params: {
    cycleId: number;
    dimension: string;
    rowValue: string;
    colValue: string;
    limit?: number;
    offset?: number;
  }): Promise<FlowsResponse> {
    return request(
      `/api/validation-cycles/matrix/flows${buildQuery({
        cycle_id: params.cycleId,
        dimension: params.dimension,
        row_value: params.rowValue,
        col_value: params.colValue,
        limit: params.limit,
        offset: params.offset,
      })}`,
    );
  },

  // Pas un appel fetch -- une URL directe pour un <a href download> (2026-09-03) : le
  // téléchargement d'un vrai fichier binaire n'a pas besoin de passer par `request()`.
  actionChangeFicheUrl(historyId: number): string {
    return `${API_BASE_URL}/api/validation-history/${historyId}/fiche.pdf`;
  },

  // "Déclarer la réclamation" (2026-09-10) -- distinct de "Changer la règle" : ne prend
  // aucune décision, constate juste qu'une décision déjà prise n'est toujours pas appliquée.
  getRuleEnforcementClaim(flowId: number): Promise<RuleEnforcementClaimOut | null> {
    return request(`/api/flows/${flowId}/rule-enforcement-claim`);
  },

  declareRuleEnforcementClaim(flowId: number): Promise<RuleEnforcementClaimOut> {
    return request(`/api/flows/${flowId}/rule-enforcement-claims`, { method: "POST" });
  },

  ruleEnforcementClaimFicheUrl(claimId: number): string {
    return `${API_BASE_URL}/api/rule-enforcement-claims/${claimId}/fiche.pdf`;
  },

  // --- Politiques de sous-réseau (2026-09-10) -- fonctionnalité isolée, voir api/types.ts.

  getObservedSubnets(source: string, prefixLength?: number): Promise<SubnetObservationsResponse> {
    return request(`/api/network-policies/subnets${buildQuery({ source, prefix_length: prefixLength })}`);
  },

  createNetworkPolicy(payload: NetworkPolicyCreate): Promise<NetworkPolicyOut> {
    return request(`/api/network-policies`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getNetworkPolicies(params: { source?: string; limit?: number; offset?: number } = {}): Promise<NetworkPoliciesResponse> {
    return request(`/api/network-policies${buildQuery(params)}`);
  },

  networkPolicyFicheUrl(policyId: number): string {
    return `${API_BASE_URL}/api/network-policies/${policyId}/fiche.pdf`;
  },
};

export { ApiError };

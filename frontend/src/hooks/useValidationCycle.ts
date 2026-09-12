import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { FlowDiffFilters, FlowFilterValues } from "../api/types";

export function useValidationCycleDiff(filters: FlowDiffFilters, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["validation-cycle-diff", filters],
    queryFn: () => api.getValidationCycleDiff(filters),
    enabled: options?.enabled ?? true,
  });
}

export function useValidationCycleCellDiff(dimension: string, filters: FlowFilterValues, enabled: boolean) {
  return useQuery({
    queryKey: ["validation-cycle-cell-diff", dimension, filters],
    queryFn: () => api.getValidationCycleCellDiff(dimension, filters),
    enabled,
  });
}

// Fusion "Politiques de sous-réseau" -> Cycle de validation (2026-09-11, demande de
// l'encadrant) -- tableau principal de ValidationCyclePage.tsx, regroupé par CIDR observé.
export function useValidationCycleSubnetDiff(source: string, prefixLength: number) {
  return useQuery({
    queryKey: ["validation-cycle-subnet-diff", source, prefixLength],
    queryFn: () => api.getValidationCycleSubnetDiff(source, prefixLength),
    enabled: !!source,
  });
}

export function useCloseValidationCycle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { source: string; closedBy?: string; note?: string }) => api.closeValidationCycle(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-diff"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-cell-diff"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-subnet-diff"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycles"] });
      queryClient.invalidateQueries({ queryKey: ["validated-matrix"] });
    },
  });
}

export function useValidationCycles(source?: string, limit?: number) {
  return useQuery({
    queryKey: ["validation-cycles", source, limit],
    queryFn: () => api.getValidationCycles({ source, limit }),
  });
}

// Matrice Validée -- reconstruite depuis les FlowSnapshot figés, jamais depuis les Flow en
// direct. `enabled` : ne tire la requête que si une source est choisie (un cycle est
// toujours propre à une source, cf. docs/13-cycle-de-validation.md).
export function useValidatedMatrix(source: string, dimension: string) {
  return useQuery({
    queryKey: ["validated-matrix", source, dimension],
    queryFn: () => api.getValidatedMatrix(source, dimension),
    enabled: !!source,
  });
}

// Drill-down d'une cellule de la Matrice Validée (2026-09-09, demande de l'encadrant) -- lit
// FlowSnapshot du cycle précis affiché, jamais Flow en direct (sinon la liste ne
// correspondrait plus à ce que montre la cellule si des Flow ont changé depuis).
export function useValidatedMatrixFlowsCell(params: {
  cycleId: number | undefined;
  dimension: string;
  rowValue: string | undefined;
  colValue: string | undefined;
}) {
  const enabled = params.cycleId !== undefined && !!params.rowValue && !!params.colValue;
  return useQuery({
    queryKey: ["validated-matrix-flows", params.cycleId, params.dimension, params.rowValue, params.colValue],
    queryFn: () =>
      api.getValidatedMatrixFlows({
        cycleId: params.cycleId as number,
        dimension: params.dimension,
        rowValue: params.rowValue as string,
        colValue: params.colValue as string,
        limit: 500,
      }),
    enabled,
  });
}

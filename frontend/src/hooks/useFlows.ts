import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { FlowsFilters, ValidationUpdate } from "../api/types";

export function useFlows(filters: FlowsFilters, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["flows", filters],
    queryFn: () => api.getFlows(filters),
    enabled: options?.enabled ?? true,
  });
}

export function useValidateFlow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ flowId, payload }: { flowId: number; payload: ValidationUpdate }) =>
      api.validateFlow(flowId, payload),
    onSuccess: () => {
      // Rafraîchit toute liste de flows affichée (table plate, drill-down matrice) et
      // l'historique -- plus simple et plus sûr qu'une mise à jour locale ciblée.
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["validation-history"] });
    },
  });
}

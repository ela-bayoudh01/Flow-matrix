import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

// "Déclarer la réclamation" (2026-09-10, demande de l'encadrant) -- flux "Règle non
// appliquée" : ne prend aucune décision (contrairement à "Changer la règle"), constate juste
// qu'une décision déjà prise n'est toujours pas appliquée par le pare-feu.
export function useRuleEnforcementClaim(flowId: number | null) {
  return useQuery({
    queryKey: ["rule-enforcement-claim", flowId],
    queryFn: () => api.getRuleEnforcementClaim(flowId as number),
    enabled: flowId !== null,
  });
}

export function useDeclareRuleEnforcementClaim() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (flowId: number) => api.declareRuleEnforcementClaim(flowId),
    onSuccess: (_data, flowId) => {
      queryClient.invalidateQueries({ queryKey: ["rule-enforcement-claim", flowId] });
    },
  });
}

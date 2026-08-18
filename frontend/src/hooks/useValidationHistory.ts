import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useValidationHistory(flowId?: number) {
  return useQuery({
    queryKey: ["validation-history", flowId],
    // Volume attendu faible en V1 (cf. docs/08-historique-des-validations.md) -- une seule
    // page de 500 suffit, pas besoin de pagination serveur pour l'instant.
    queryFn: () => api.getValidationHistory({ flowId, limit: 500 }),
  });
}

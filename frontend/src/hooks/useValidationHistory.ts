import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ValidationHistoryFilters } from "../api/types";

// Filtres étendus (2026-09-12, demande de l'encadrant après démo) -- source/plage de dates/
// type de changement, en plus de la recherche par mot-clé déjà existante. Signature changée
// de (flowId?, q?) à un objet de filtres unique : seul appelant, HistoryPage.tsx.
export function useValidationHistory(filters: ValidationHistoryFilters = {}) {
  return useQuery({
    queryKey: ["validation-history", filters],
    // Volume attendu faible en V1 (cf. docs/08-historique-des-validations.md) -- une seule
    // page de 500 suffit, pas besoin de pagination serveur pour l'instant.
    queryFn: () => api.getValidationHistory({ limit: 500, ...filters }),
  });
}

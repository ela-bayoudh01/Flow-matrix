import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { FlowsFilters, RuleChangeUpdate, ValidationUpdate } from "../api/types";

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
      // Rafraîchit toute liste de flows affichée (table plate, drill-down matrice), la page
      // Cycle de validation (diff par flux et par cellule, qui affichent aussi le statut de
      // validation) et l'historique -- plus simple et plus sûr qu'une mise à jour locale
      // ciblée. Oubli réel constaté (2026-08-21) : sans invalider validation-cycle-diff, le
      // statut "approved"/"blocked" n'apparaissait qu'après un rechargement manuel de page.
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["validation-history"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-diff"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-cell-diff"] });
      // Rollup par sous-réseau (2026-09-11) -- même oubli déjà fait deux fois ci-dessus pour
      // le diff par flux/cellule, évité ici dès le départ : sans ça, les compteurs "2 Nouveau
      // · 1 Règle non appliquée" du tableau des sous-réseaux resteraient périmés après une
      // action Valider/Bloquer/Changer la règle/qualification.
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-subnet-diff"] });
    },
  });
}

// Bouton dédié "Changer la règle" (2026-09-05) -- distinct de useValidateFlow (Valider/
// Bloquer, toujours immédiat) : seul chemin qui fige decided_action + justification et
// produit une fiche PDF. Mêmes invalidations que useValidateFlow (même surface affectée :
// table plate, Cycle de validation, historique).
export function useChangeFlowRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ flowId, payload }: { flowId: number; payload: RuleChangeUpdate }) =>
      api.changeFlowRule(flowId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["validation-history"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-diff"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-cell-diff"] });
      // Rollup par sous-réseau (2026-09-11) -- même oubli déjà fait deux fois ci-dessus pour
      // le diff par flux/cellule, évité ici dès le départ : sans ça, les compteurs "2 Nouveau
      // · 1 Règle non appliquée" du tableau des sous-réseaux resteraient périmés après une
      // action Valider/Bloquer/Changer la règle/qualification.
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-subnet-diff"] });
    },
  });
}

// source optionnel (2026-09-09) -- fixé au niveau du hook (pas de la variable de mutate())
// pour que mutate() reste appelable sans argument partout où c'est déjà le cas (Import, Table
// des flux, qui qualifient tout l'historique) : useQualifyFlows(source) scope à une seule
// source (bandeau "flux non qualifiés" du Cycle de validation), useQualifyFlows() qualifie tout.
export function useQualifyFlows(source?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.qualifyFlows(source),
    onSuccess: () => {
      // criticality_label change sur les Flow -- toute vue qui en dépend doit se rafraîchir :
      // table plate, matrice (dimensions "*_criticality" et mode de coloration Criticité), le
      // Dashboard (cartes + graphique de répartition), ET le Cycle de validation
      // (criticality_label fait partie de STRUCTURAL_FIELDS -- oubli réel constaté le
      // 2026-09-09 en câblant le bandeau "flux non qualifiés" : sans ces deux invalidations,
      // le diff ne se rafraîchissait qu'après un rechargement manuel de page).
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["matrix"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-diff"] });
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-cell-diff"] });
      // Rollup par sous-réseau (2026-09-11) -- même oubli déjà fait deux fois ci-dessus pour
      // le diff par flux/cellule, évité ici dès le départ : sans ça, les compteurs "2 Nouveau
      // · 1 Règle non appliquée" du tableau des sous-réseaux resteraient périmés après une
      // action Valider/Bloquer/Changer la règle/qualification.
      queryClient.invalidateQueries({ queryKey: ["validation-cycle-subnet-diff"] });
    },
  });
}

import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

// Liste des sources connues (firewalls/sites), dérivée de GET /api/sources -- jamais une
// liste de vrais noms de sites Nouvelair codée en dur (même principe que useZoneOptions.ts et
// le filtre "Source (site)" de FilterBar).
//
// 2026-09-12, bug réel corrigé, signalé juste après une clôture de cycle : dérivait
// auparavant de useMatrix("source_zone", {}) (GET /api/matrix), qui exclut désormais les Flow
// inactifs depuis la dernière clôture (Services/matrix_engine.py::build_matrix, correctif du
// même jour). Une source dont TOUS les flux venaient d'être clôturés (aucun nouvel import
// depuis) disparaissait donc entièrement du sélecteur -- impossible de choisir sa propre
// Matrice Validée ou de préparer son prochain cycle juste après l'action normale de clôturer.
// /api/sources (flows_query.list_known_sources) est volontairement indépendant de toute
// notion de cycle : une source existe dès qu'elle a au moins un Flow, point final.
export function useSourceOptions(): string[] {
  const { data } = useQuery({
    queryKey: ["sources"],
    queryFn: () => api.getSources(),
  });
  return data?.sources ?? [];
}

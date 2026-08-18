import { useMemo } from "react";
import { useMatrix } from "./useMatrix";

// Liste des zones connues, dérivée de la matrice NON filtrée (toujours toutes les zones
// possibles, même si un filtre est actif ailleurs -- sinon sélectionner un filtre ferait
// disparaître des options du menu déroulant). Réutilise le cache TanStack Query : si
// MatrixPage a déjà chargé la matrice sans filtre, aucun appel réseau supplémentaire.
export function useZoneOptions(): string[] {
  const { data } = useMatrix("zone", {});
  return useMemo(() => {
    if (!data) return [];
    const zones = new Set<string>();
    for (const cell of data.cells) {
      if (cell.row) zones.add(cell.row);
      if (cell.col) zones.add(cell.col);
    }
    return [...zones].sort();
  }, [data]);
}

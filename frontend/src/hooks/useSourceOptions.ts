import { useMemo } from "react";
import { useMatrix } from "./useMatrix";

// Liste des sources connues (firewalls/sites), dérivée dynamiquement de la dimension
// "source_zone" de la matrice -- jamais une liste de vrais noms de sites Nouvelair codée en
// dur (même principe que useZoneOptions.ts et le filtre "Source (site)" de FilterBar).
export function useSourceOptions(): string[] {
  const { data } = useMatrix("source_zone", {});
  return useMemo(() => {
    if (!data) return [];
    const sources = new Set<string>();
    for (const cell of data.cells) {
      if (cell.row) sources.add(cell.row);
    }
    return [...sources].sort();
  }, [data]);
}

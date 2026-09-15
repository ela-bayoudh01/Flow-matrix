import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SourceCoverageOut } from "../api/types";

// Période couverte + dernier import par source (2026-09-12, demande de l'encadrant après
// démo) -- une seule requête, réutilisée par le Dashboard (toutes les sources), la Matrice et
// la Table des flux (la source actuellement filtrée, via useSourceCoverageFor ci-dessous).
export function useSourceCoverage() {
  return useQuery({
    queryKey: ["source-coverage"],
    queryFn: () => api.getSourceCoverage(),
  });
}

// Pratique pour Matrice/Table des flux, qui n'ont besoin que de l'entrée correspondant à la
// source actuellement filtrée (ou undefined si aucune source choisie/pas encore chargé) --
// même requête partagée que useSourceCoverage ci-dessus (React Query dédoublonne), jamais un
// second appel réseau.
export function useSourceCoverageFor(source: string | undefined): SourceCoverageOut | undefined {
  const { data } = useSourceCoverage();
  return useMemo(() => data?.items.find((item) => item.source === source), [data, source]);
}

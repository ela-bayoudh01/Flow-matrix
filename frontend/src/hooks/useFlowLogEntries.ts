import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

// Drill-down (2026-09-06, demande de l'encadrant) : connexions individuelles sous-jacentes à
// un Flow -- occurrence_count agrège potentiellement des milliers de LogEntry, jamais
// consultables un par un jusqu'ici. `flowId` null tant que le panneau n'est pas ouvert --
// `enabled` évite tout appel réseau inutile.
export function useFlowLogEntries(flowId: number | null, params: { limit: number; offset: number }) {
  return useQuery({
    queryKey: ["flow-log-entries", flowId, params.limit, params.offset],
    queryFn: () => api.getFlowLogEntries(flowId as number, params),
    enabled: flowId !== null,
  });
}

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

// `uploadProgress` couvre uniquement la phase d'envoi (0-100) -- une fois à 100, la mutation
// reste "pending" pendant que le serveur traite le fichier (peut prendre plusieurs minutes
// sur un gros fichier, cf. docs/04-ingestion-et-flow-engine.md) : c'est la 2e phase,
// indéterminée, affichée séparément par ImportPage.tsx.
export function useImportLogs() {
  const queryClient = useQueryClient();
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

  const mutation = useMutation({
    mutationFn: (file: File) => {
      setUploadProgress(0);
      return api.importLogs(file, setUploadProgress);
    },
    onSuccess: () => {
      setUploadProgress(null);
      // Nouveaux Flow -- toute vue qui en dépend doit se rafraîchir.
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["matrix"] });
      // Historique des imports (2026-09-11) -- la nouvelle ligne doit apparaître immédiatement,
      // sans attendre un rechargement manuel de la page.
      queryClient.invalidateQueries({ queryKey: ["import-history"] });
    },
    onError: () => {
      setUploadProgress(null);
    },
  });

  return { ...mutation, uploadProgress };
}

// Historique des imports (2026-09-11, demande de l'encadrant) -- nom distinct de
// useImportLogs ci-dessus (la mutation d'upload) : cette requête est INDÉPENDANTE de l'état
// de cette mutation, c'est précisément ce qui lui permet de rester visible même après avoir
// navigué ailleurs et être revenu sur la page Import (voir ImportPage.tsx).
export function useImportHistory(limit = 50) {
  return useQuery({
    queryKey: ["import-history", limit],
    queryFn: () => api.getImportLogs({ limit }),
  });
}

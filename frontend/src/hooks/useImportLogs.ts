import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
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
    },
    onError: () => {
      setUploadProgress(null);
    },
  });

  return { ...mutation, uploadProgress };
}

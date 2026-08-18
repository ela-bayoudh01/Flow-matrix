import { useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import { useRecommendations, useRunRecommendations } from "../hooks/useRecommendations";
import { RecommendationsTable } from "../components/recommendations/RecommendationsTable";
import { RecommendationsLegend } from "../components/recommendations/RecommendationsLegend";
import { RecommendationDetailDrawer } from "../components/recommendations/RecommendationDetailDrawer";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { FINDING_TYPE_LABELS } from "../theme/colors";
import type { RecommendationFilters } from "../api/types";

const STATUS_OPTIONS = ["pending", "acknowledged", "dismissed"];

export function RecommendationsPage() {
  // "pending" par défaut : les findings déjà traités/rejetés n'ont pas besoin d'encombrer
  // la vue de travail quotidienne (même logique que HistoryPage pour l'état vide explicite).
  const [filters, setFilters] = useState<RecommendationFilters>({ status: "pending" });
  // Seul l'id est gardé en état : le panneau de détail dérive toujours l'objet à jour depuis
  // `data.items` (pas une copie figée au moment du clic), sinon "Traiter"/"Rejeter" laisse le
  // panneau afficher l'ancien statut et les boutons alors que la liste, elle, est déjà à jour.
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data, isLoading, isError, error } = useRecommendations(filters);
  const runRecommendations = useRunRecommendations();
  const selected = data?.items.find((r) => r.id === selectedId) ?? null;

  function set<K extends keyof RecommendationFilters>(key: K, raw: string) {
    setFilters({ ...filters, [key]: raw === "" ? undefined : raw });
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Recommandations
      </Typography>

      <RecommendationsLegend />

      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center", mb: 2 }}>
        <TextField
          select
          size="small"
          label="Statut"
          value={filters.status ?? ""}
          onChange={(e) => set("status", e.target.value)}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">Tous</MenuItem>
          {STATUS_OPTIONS.map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          size="small"
          label="Type"
          value={filters.finding_type ?? ""}
          onChange={(e) => set("finding_type", e.target.value)}
          sx={{ minWidth: 190 }}
        >
          <MenuItem value="">Tous</MenuItem>
          {Object.entries(FINDING_TYPE_LABELS).map(([type, label]) => (
            <MenuItem key={type} value={type}>
              {label}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          size="small"
          label="Source (site)"
          value={filters.source ?? ""}
          onChange={(e) => set("source", e.target.value)}
          sx={{ minWidth: 160 }}
        />

        <Button
          variant="contained"
          size="small"
          loading={runRecommendations.isPending}
          onClick={() => runRecommendations.mutate()}
        >
          Lancer l'analyse
        </Button>
      </Stack>

      {runRecommendations.isSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => runRecommendations.reset()}>
          Analyse terminée : {runRecommendations.data.total_findings} finding(s) au total (
          {runRecommendations.data.created} créé(s), {runRecommendations.data.updated} mis à jour)
          {!runRecommendations.data.obsolete_detection_enabled &&
            " -- détection \"obsolète\" désactivée, fenêtre d'observation trop courte"}
          .
        </Alert>
      )}
      {runRecommendations.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(runRecommendations.error as Error).message}
        </Alert>
      )}

      {isLoading && <TableSkeleton />}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data && data.items.length === 0 && (
        <Alert severity="info">
          Aucune recommandation pour ces filtres -- lance une analyse si aucune n'a encore été
          exécutée, ou élargis le filtre de statut.
        </Alert>
      )}

      {data && data.items.length > 0 && (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {data.total_count} recommandation(s)
          </Typography>
          <RecommendationsTable items={data.items} onRowClicked={(r) => setSelectedId(r.id)} />
        </>
      )}

      <RecommendationDetailDrawer recommendation={selected} onClose={() => setSelectedId(null)} />
    </Box>
  );
}

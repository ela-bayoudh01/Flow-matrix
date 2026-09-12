import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import { useState } from "react";
import { useFlows, useQualifyFlows } from "../hooks/useFlows";
import { useSourceOptions } from "../hooks/useSourceOptions";
import { FlowsTable } from "../components/flows/FlowsTable";
import { FlowsSummaryBar } from "../components/flows/FlowsSummaryBar";
import { FilterBar } from "../components/filters/FilterBar";
import { KeywordSearchField } from "../components/common/KeywordSearchField";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { StatCardsSkeleton } from "../components/common/StatCardsSkeleton";
import type { FlowFilterValues } from "../api/types";

export function FlowsTablePage() {
  const [filters, setFilters] = useState<FlowFilterValues>({});
  const [q, setQ] = useState("");
  const { data, isLoading, isError, error } = useFlows({ ...filters, q, limit: 500 });
  const qualifyFlows = useQualifyFlows();
  // Filtre "Source (firewall)" (2026-09-11, demande de l'encadrant) -- même principe que le
  // sélecteur de ValidationCyclePage.tsx (liste déroulante dérivée de useSourceOptions,
  // jamais une liste codée en dur), mais optionnel ici : "Toutes" par défaut, pas de source
  // imposée -- Table des flux continue d'accumuler et d'afficher tous les firewalls importés
  // ensemble tant que rien n'est choisi. Pilote directement filters.source (même clé que le
  // champ libre "Source (site)" de FilterBar, masqué ci-dessous via hideSourceFilter pour
  // éviter deux contrôles concurrents sur le même filtre).
  const sourceOptions = useSourceOptions();

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 2, flexWrap: "wrap" }}>
        <Typography variant="h5">Table des flux</Typography>
        <TextField
          select
          size="small"
          label="Source (firewall)"
          value={filters.source ?? ""}
          onChange={(e) => setFilters({ ...filters, source: e.target.value || undefined })}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">Toutes les sources</MenuItem>
          {sourceOptions.map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </TextField>
        <KeywordSearchField value={q} onChange={setQ} />
        <Button
          variant="outlined"
          size="small"
          loading={qualifyFlows.isPending}
          onClick={() => qualifyFlows.mutate()}
        >
          Lancer la qualification
        </Button>
      </Stack>

      {qualifyFlows.isSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => qualifyFlows.reset()}>
          Qualification terminée : {qualifyFlows.data.total_qualified} flux qualifié(s) --{" "}
          {Object.entries(qualifyFlows.data.label_counts)
            .map(([label, count]) => `${label} : ${count}`)
            .join(", ")}
          .
        </Alert>
      )}
      {qualifyFlows.isSuccess && qualifyFlows.data.unclassified_zones.length > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Zones non classées détectées : {qualifyFlows.data.unclassified_zones.join(", ")}. Le
          score de criticité des flux concernés est calculé par défaut (sans savoir s'il s'agit
          d'une zone interne ou externe) -- à vérifier avant de considérer ces résultats comme
          fiables, en classant ces zones dans ZONE_ROLES.
        </Alert>
      )}
      {qualifyFlows.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(qualifyFlows.error as Error).message}
        </Alert>
      )}

      <FilterBar value={filters} onChange={setFilters} hideSourceFilter />

      {isLoading && (
        <>
          <Box sx={{ mb: 2 }}>
            <StatCardsSkeleton />
          </Box>
          <TableSkeleton />
        </>
      )}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data && (
        <>
          <FlowsSummaryBar summary={data.summary} />
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {data.items.length} affichés sur {data.total_count} au total
          </Typography>
          <FlowsTable flows={data.items} />
        </>
      )}
    </Box>
  );
}

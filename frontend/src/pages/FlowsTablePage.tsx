import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useFlows, useQualifyFlows } from "../hooks/useFlows";
import { FlowsTable } from "../components/flows/FlowsTable";
import { FlowsSummaryBar } from "../components/flows/FlowsSummaryBar";
import { FilterBar } from "../components/filters/FilterBar";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { StatCardsSkeleton } from "../components/common/StatCardsSkeleton";
import type { FlowFilterValues } from "../api/types";

export function FlowsTablePage() {
  const [filters, setFilters] = useState<FlowFilterValues>({});
  const { data, isLoading, isError, error } = useFlows({ ...filters, limit: 500 });
  const qualifyFlows = useQualifyFlows();

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 2 }}>
        <Typography variant="h5">Table des flux</Typography>
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

      <FilterBar value={filters} onChange={setFilters} />

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

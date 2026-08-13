import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { useFlows } from "../hooks/useFlows";
import { FlowsTable } from "../components/flows/FlowsTable";
import { FlowsSummaryBar } from "../components/flows/FlowsSummaryBar";
import { FilterBar } from "../components/filters/FilterBar";
import type { FlowFilterValues } from "../api/types";

export function FlowsTablePage() {
  const [filters, setFilters] = useState<FlowFilterValues>({});
  const { data, isLoading, isError, error } = useFlows({ ...filters, limit: 500 });

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Table des flux
      </Typography>

      <FilterBar value={filters} onChange={setFilters} />

      {isLoading && <CircularProgress />}
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

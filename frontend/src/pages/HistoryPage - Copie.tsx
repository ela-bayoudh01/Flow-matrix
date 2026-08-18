import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type ColDef } from "ag-grid-community";
import { useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import { useValidationHistory } from "../hooks/useValidationHistory";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { appGridTheme } from "../theme/agGridTheme";
import type { ValidationHistoryOut } from "../api/types";

ModuleRegistry.registerModules([AllCommunityModule]);

export function HistoryPage() {
  const { data, isLoading, isError, error } = useValidationHistory();

  const columnDefs = useMemo<ColDef<ValidationHistoryOut>[]>(
    () => [
      { field: "created_at", headerName: "Date", width: 190 },
      { field: "source", headerName: "Source", width: 150 },
      {
        headerName: "Flux",
        width: 280,
        valueGetter: (p) =>
          p.data ? `${p.data.src_ip} -> ${p.data.dst_ip}:${p.data.dst_port ?? "?"} (${p.data.protocol})` : "",
      },
      {
        headerName: "Changement",
        width: 200,
        valueGetter: (p) => (p.data ? `${p.data.old_status ?? "—"} -> ${p.data.new_status}` : ""),
      },
      { field: "validated_by", headerName: "Validé par", width: 150 },
    ],
    [],
  );

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Historique des validations
      </Typography>

      {isLoading && <TableSkeleton />}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data && data.items.length === 0 && (
        <Alert severity="info">
          Aucune validation enregistrée pour l'instant -- cette page s'alimente automatiquement dès qu'un flux est
          validé ou bloqué depuis la table des flux ou la matrice.
        </Alert>
      )}

      {data && data.items.length > 0 && (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {data.total_count} changement(s) de statut enregistré(s)
          </Typography>
          <div style={{ height: 600, width: "100%" }}>
            <AgGridReact<ValidationHistoryOut>
              theme={appGridTheme}
              rowData={data.items}
              columnDefs={columnDefs}
              defaultColDef={{ sortable: true, filter: true, resizable: true }}
              pagination
              paginationPageSize={50}
            />
          </div>
        </>
      )}
    </Box>
  );
}

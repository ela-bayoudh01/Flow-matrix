import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type CellClickedEvent, type ColDef } from "ag-grid-community";
import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import DownloadIcon from "@mui/icons-material/Download";
import { useValidationHistory } from "../hooks/useValidationHistory";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { KeywordSearchField } from "../components/common/KeywordSearchField";
import { ValidationHistoryDetailDrawer } from "../components/history/ValidationHistoryDetailDrawer";
import { appGridTheme } from "../theme/agGridTheme";
import { api } from "../api/client";
import type { ValidationHistoryOut } from "../api/types";

ModuleRegistry.registerModules([AllCommunityModule]);

export function HistoryPage() {
  const [q, setQ] = useState("");
  const [selectedEntry, setSelectedEntry] = useState<ValidationHistoryOut | null>(null);
  const { data, isLoading, isError, error } = useValidationHistory(undefined, q);

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
      {
        headerName: "Justification",
        width: 220,
        valueGetter: (p) => p.data?.justification ?? "",
        tooltipValueGetter: (p) => (p.value ? String(p.value) : undefined),
      },
      {
        colId: "fiche",
        headerName: "Fiche",
        width: 190,
        sortable: false,
        filter: false,
        cellStyle: undefined, // jamais le curseur "pointer" ici -- ne déclenche jamais l'ouverture du panneau
        cellRenderer: (p: { data?: ValidationHistoryOut }) =>
          p.data?.justification ? (
            <Button
              size="small"
              startIcon={<DownloadIcon />}
              component="a"
              href={api.actionChangeFicheUrl(p.data.id)}
              download
            >
              Télécharger
            </Button>
          ) : null,
      },
    ],
    [],
  );

  // Toute la ligne ouvre le panneau de détail (bug réel signalé le 2026-09-05 : aucun moyen
  // de consulter/télécharger la fiche d'un changement de règle depuis cette page) -- exclut
  // la colonne Fiche : cliquer Télécharger ne doit jamais aussi ouvrir le panneau.
  function handleCellClicked(event: CellClickedEvent<ValidationHistoryOut>) {
    if (!event.data) return;
    if (event.column.getColId() === "fiche") return;
    setSelectedEntry(event.data);
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 2, flexWrap: "wrap" }}>
        <Typography variant="h5">Historique des validations</Typography>
        <KeywordSearchField value={q} onChange={setQ} />
      </Stack>

      {isLoading && <TableSkeleton />}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data && data.items.length === 0 && q && (
        <Alert severity="info">Aucune validation ne correspond à "{q}".</Alert>
      )}
      {data && data.items.length === 0 && !q && (
        <Alert severity="info">
          Aucune validation enregistrée pour l'instant
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
              defaultColDef={{ sortable: true, filter: true, resizable: true, cellStyle: { cursor: "pointer" } }}
              pagination
              paginationPageSize={50}
              onCellClicked={handleCellClicked}
            />
          </div>
        </>
      )}

      <ValidationHistoryDetailDrawer entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
    </Box>
  );
}

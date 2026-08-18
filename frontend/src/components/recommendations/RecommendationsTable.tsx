import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type ColDef } from "ag-grid-community";
import { useMemo } from "react";
import Chip from "@mui/material/Chip";
import type { RuleRecommendationOut } from "../../api/types";
import { FINDING_TYPE_LABELS, FINDING_TYPE_COLORS, validationStatusColor } from "../../theme/colors";
import { appGridTheme } from "../../theme/agGridTheme";

ModuleRegistry.registerModules([AllCommunityModule]);

function FindingTypeChip({ findingType }: { findingType: string }) {
  return (
    <Chip
      size="small"
      label={FINDING_TYPE_LABELS[findingType] ?? findingType}
      sx={{ backgroundColor: FINDING_TYPE_COLORS[findingType] ?? "#9e9e9e", color: "#fff" }}
    />
  );
}

function StatusChip({ status }: { status: string }) {
  return (
    <Chip size="small" variant="outlined" label={status} sx={{ borderColor: validationStatusColor(status), color: validationStatusColor(status) }} />
  );
}

interface RecommendationsTableProps {
  items: RuleRecommendationOut[];
  onRowClicked: (recommendation: RuleRecommendationOut) => void;
}

export function RecommendationsTable({ items, onRowClicked }: RecommendationsTableProps) {
  const columnDefs = useMemo<ColDef<RuleRecommendationOut>[]>(
    () => [
      {
        headerName: "Type",
        width: 190,
        cellRenderer: (p: { data?: RuleRecommendationOut }) =>
          p.data ? <FindingTypeChip findingType={p.data.finding_type} /> : null,
      },
      { field: "source", headerName: "Source", width: 150 },
      {
        headerName: "Règle / Zones",
        width: 260,
        valueGetter: (p) =>
          p.data?.finding_type === "sans_regle_explicite"
            ? `${p.data.ingress_zone} → ${p.data.egress_zone}`
            : p.data?.rule_name,
      },
      { field: "flow_count", headerName: "Flux concernés", width: 130 },
      {
        headerName: "Statut",
        width: 140,
        cellRenderer: (p: { data?: RuleRecommendationOut }) => (p.data ? <StatusChip status={p.data.status} /> : null),
      },
      { field: "created_at", headerName: "Détecté le", width: 190 },
      { field: "updated_at", headerName: "Mis à jour le", width: 190 },
    ],
    [],
  );

  return (
    <div style={{ height: 600, width: "100%" }}>
      <AgGridReact<RuleRecommendationOut>
        theme={appGridTheme}
        rowData={items}
        columnDefs={columnDefs}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        autoSizeStrategy={{ type: "fitCellContents" }}
        pagination
        paginationPageSize={50}
        onRowClicked={(e) => e.data && onRowClicked(e.data)}
      />
    </div>
  );
}

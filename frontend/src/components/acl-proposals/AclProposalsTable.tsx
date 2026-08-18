import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type ColDef } from "ag-grid-community";
import { useMemo } from "react";
import Chip from "@mui/material/Chip";
import type { AclProposalOut } from "../../api/types";
import { INTENT_LABELS, INTENT_COLORS, validationStatusColor } from "../../theme/colors";
import { appGridTheme } from "../../theme/agGridTheme";

ModuleRegistry.registerModules([AllCommunityModule]);

function IntentChip({ intent }: { intent: string }) {
  return (
    <Chip
      size="small"
      label={INTENT_LABELS[intent] ?? intent}
      sx={{ backgroundColor: INTENT_COLORS[intent] ?? "#9e9e9e", color: "#fff" }}
    />
  );
}

function StatusChip({ status }: { status: string }) {
  return (
    <Chip size="small" variant="outlined" label={status} sx={{ borderColor: validationStatusColor(status), color: validationStatusColor(status) }} />
  );
}

interface AclProposalsTableProps {
  items: AclProposalOut[];
  onRowClicked: (proposal: AclProposalOut) => void;
}

export function AclProposalsTable({ items, onRowClicked }: AclProposalsTableProps) {
  const columnDefs = useMemo<ColDef<AclProposalOut>[]>(
    () => [
      {
        headerName: "Type",
        width: 150,
        cellRenderer: (p: { data?: AclProposalOut }) => (p.data ? <IntentChip intent={p.data.intent} /> : null),
      },
      { field: "source", headerName: "Source", width: 150 },
      {
        headerName: "Zones / Règle ciblée",
        width: 260,
        wrapHeaderText: true,
        autoHeaderHeight: true,
        valueGetter: (p) =>
          p.data?.intent === "tighten" || p.data?.intent === "revoke"
            ? p.data.target_rule_name
            : `${p.data?.ingress_zone} → ${p.data?.egress_zone}`,
      },
      { field: "proposed_action", headerName: "Action proposée", width: 150 },
      {
        headerName: "Statut",
        width: 130,
        cellRenderer: (p: { data?: AclProposalOut }) => (p.data ? <StatusChip status={p.data.status} /> : null),
      },
      { field: "created_at", headerName: "Créé/ajouté le", width: 190 },
    ],
    [],
  );

  return (
    <div style={{ height: 600, width: "100%" }}>
      <AgGridReact<AclProposalOut>
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

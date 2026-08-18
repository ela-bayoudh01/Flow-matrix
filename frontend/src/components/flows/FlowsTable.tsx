import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type ColDef } from "ag-grid-community";
import { useMemo } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import type { FlowOut } from "../../api/types";
import { useValidateFlow } from "../../hooks/useFlows";
import { criticalityColor, validationStatusColor, ACTION_COLORS } from "../../theme/colors";
import { appGridTheme } from "../../theme/agGridTheme";

ModuleRegistry.registerModules([AllCommunityModule]);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  const units = ["Ko", "Mo", "Go", "To"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

// Indicateur, pas un mode de coloration ni une nouvelle détection : une forte asymétrie sur
// un port/une zone inhabituels peut être un signal d'exfiltration ou de téléchargement massif
// -- laissé à l'appréciation de l'analyste, jamais auto-signalé comme suspect (même principe
// que le reste du projet : explicable, jamais une décision prise à la place de l'humain).
function asymmetryLabel(initiatorBytes: number, responderBytes: number): string {
  const total = initiatorBytes + responderBytes;
  if (total === 0) return "—";
  const initiatorPct = Math.round((initiatorBytes / total) * 100);
  return `${initiatorPct}% envoyé / ${100 - initiatorPct}% reçu`;
}

function ActionChip({ action }: { action: string | null }) {
  if (!action) return null;
  return <Chip size="small" label={action} sx={{ backgroundColor: ACTION_COLORS[action] ?? "#9e9e9e", color: "#fff" }} />;
}

function CriticalityChip({ label }: { label: string | null }) {
  if (!label) return null;
  return <Chip size="small" label={label} sx={{ backgroundColor: criticalityColor(label), color: "#fff" }} />;
}

function ValidationCell({ flow }: { flow: FlowOut }) {
  const validateFlow = useValidateFlow();

  if (flow.validation_status !== "pending") {
    return (
      <Chip
        size="small"
        variant="outlined"
        label={flow.validation_status}
        sx={{ borderColor: validationStatusColor(flow.validation_status), color: validationStatusColor(flow.validation_status) }}
      />
    );
  }

  return (
    <Stack direction="row" spacing={1}>
      <Button
        size="small"
        color="success"
        variant="outlined"
        loading={validateFlow.isPending}
        onClick={() => validateFlow.mutate({ flowId: flow.id, payload: { status: "approved" } })}
      >
        Valider
      </Button>
      <Button
        size="small"
        color="error"
        variant="outlined"
        loading={validateFlow.isPending}
        onClick={() => validateFlow.mutate({ flowId: flow.id, payload: { status: "blocked" } })}
      >
        Bloquer
      </Button>
    </Stack>
  );
}

export function FlowsTable({ flows }: { flows: FlowOut[] }) {
  const columnDefs = useMemo<ColDef<FlowOut>[]>(
    () => [
      { field: "src_ip", headerName: "Source", pinned: "left", width: 140 },
      { field: "dst_ip", headerName: "Destination", width: 140 },
      { field: "dst_port", headerName: "Port", width: 90 },
      { field: "protocol", headerName: "Protocole", width: 100 },
      {
        headerName: "Action",
        width: 110,
        cellRenderer: (p: { data?: FlowOut }) => (p.data ? <ActionChip action={p.data.dominant_action} /> : null),
      },
      { field: "occurrence_count", headerName: "Occurrences", width: 120 },
      {
        headerName: "Volume",
        width: 110,
        valueGetter: (p) =>
          p.data ? formatBytes(p.data.total_initiator_bytes + p.data.total_responder_bytes) : "",
      },
      {
        headerName: "Asymétrie envoyé/reçu",
        width: 190,
        valueGetter: (p) =>
          p.data ? asymmetryLabel(p.data.total_initiator_bytes, p.data.total_responder_bytes) : "",
      },
      { field: "first_seen_at", headerName: "Première vue", width: 170 },
      { field: "last_seen_at", headerName: "Dernière vue", width: 170 },
      {
        headerName: "Application",
        width: 170,
        valueGetter: (p) => p.data?.web_application ?? p.data?.application_protocol ?? "",
        tooltipValueGetter: (p) => (p.value ? String(p.value) : undefined),
      },
      {
        field: "last_access_control_rule_name",
        headerName: "Règle ACL",
        width: 240,
        tooltipValueGetter: (p) => (p.value ? String(p.value) : undefined),
      },
      {
        headerName: "Criticité",
        width: 120,
        cellRenderer: (p: { data?: FlowOut }) => (p.data ? <CriticalityChip label={p.data.criticality_label} /> : null),
      },
      {
        headerName: "Validation",
        width: 200,
        sortable: false,
        filter: false,
        cellRenderer: (p: { data?: FlowOut }) => (p.data ? <ValidationCell flow={p.data} /> : null),
      },
    ],
    [],
  );

  return (
    <div style={{ height: 600, width: "100%" }}>
      <AgGridReact<FlowOut>
        theme={appGridTheme}
        rowData={flows}
        columnDefs={columnDefs}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        pagination
        paginationPageSize={50}
      />
    </div>
  );
}

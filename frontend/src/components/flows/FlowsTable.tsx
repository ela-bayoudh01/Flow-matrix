import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef } from "ag-grid-community";
import { useMemo } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import type { FlowOut } from "../../api/types";
import { useValidateFlow } from "../../hooks/useFlows";

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

function ValidationCell({ flow }: { flow: FlowOut }) {
  const validateFlow = useValidateFlow();

  if (flow.validation_status !== "pending") {
    return <span>{flow.validation_status}</span>;
  }

  return (
    <Stack direction="row" spacing={1}>
      <Button
        size="small"
        color="success"
        variant="outlined"
        disabled={validateFlow.isPending}
        onClick={() => validateFlow.mutate({ flowId: flow.id, payload: { status: "approved" } })}
      >
        Valider
      </Button>
      <Button
        size="small"
        color="error"
        variant="outlined"
        disabled={validateFlow.isPending}
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
      { field: "dominant_action", headerName: "Action", width: 100 },
      { field: "occurrence_count", headerName: "Occurrences", width: 120 },
      {
        headerName: "Volume",
        width: 110,
        valueGetter: (p) =>
          p.data ? formatBytes(p.data.total_initiator_bytes + p.data.total_responder_bytes) : "",
      },
      { field: "first_seen_at", headerName: "Première vue", width: 170 },
      { field: "last_seen_at", headerName: "Dernière vue", width: 170 },
      {
        headerName: "Application",
        width: 150,
        valueGetter: (p) => p.data?.web_application ?? p.data?.application_protocol ?? "",
      },
      { field: "last_access_control_rule_name", headerName: "Règle ACL", width: 200 },
      { field: "criticality_label", headerName: "Criticité", width: 110 },
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
        theme={themeQuartz}
        rowData={flows}
        columnDefs={columnDefs}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        pagination
        paginationPageSize={50}
      />
    </div>
  );
}

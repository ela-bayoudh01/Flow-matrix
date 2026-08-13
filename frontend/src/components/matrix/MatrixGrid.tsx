import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type CellClickedEvent,
} from "ag-grid-community";
import { useMemo } from "react";
import type { MatrixCell } from "../../api/types";

ModuleRegistry.registerModules([AllCommunityModule]);

export type ColorMode = "volume" | "criticality";

// Ordre du pire au moins grave -- choix d'affichage frontend uniquement (le backend, lui,
// ne suppose délibérément aucun ordre sur criticality_label, cf. docs/07-qualification-engine.md).
// Exporté pour que MatrixLegend utilise exactement la même source de vérité (jamais deux
// définitions de couleurs qui pourraient diverger).
export const CRITICALITY_ORDER = ["critical", "high", "medium", "low"];
export const CRITICALITY_COLORS: Record<string, string> = {
  critical: "#d32f2f",
  high: "#f57c00",
  medium: "#fbc02d",
  low: "#66bb6a",
};
export const NON_QUALIFIE_COLOR = "#bdbdbd";
export const EMPTY_CELL_COLOR = "#f5f5f5"; // aucun flow entre cette paire

export function worstCriticality(breakdown: Record<string, number>): string | null {
  for (const label of CRITICALITY_ORDER) {
    if (breakdown[label] > 0) return label;
  }
  return null;
}

function volumeColor(flowCount: number, maxFlowCount: number): string {
  if (flowCount === 0) return EMPTY_CELL_COLOR;
  const ratio = maxFlowCount > 0 ? Math.log(flowCount + 1) / Math.log(maxFlowCount + 1) : 0;
  const lightness = 92 - ratio * 60; // presque blanc -> bleu foncé
  return `hsl(210, 70%, ${lightness}%)`;
}

function criticalityColor(cell: MatrixCell | undefined): string {
  if (!cell || cell.flow_count === 0) return EMPTY_CELL_COLOR;
  const worst = worstCriticality(cell.criticality_breakdown);
  return worst ? CRITICALITY_COLORS[worst] : NON_QUALIFIE_COLOR;
}

interface MatrixGridProps {
  cells: MatrixCell[];
  colorMode: ColorMode;
  onCellClick: (row: string, col: string) => void;
}

export function MatrixGrid({ cells, colorMode, onCellClick }: MatrixGridProps) {
  const { rows, cols, cellMap, maxFlowCount } = useMemo(() => {
    const rowSet = new Set<string>();
    const colSet = new Set<string>();
    const map = new Map<string, MatrixCell>();
    let max = 0;
    for (const cell of cells) {
      const rowLabel = cell.row ?? "(Non renseigné)";
      const colLabel = cell.col ?? "(Non renseigné)";
      rowSet.add(rowLabel);
      colSet.add(colLabel);
      map.set(`${rowLabel}::${colLabel}`, cell);
      if (cell.flow_count > max) max = cell.flow_count;
    }
    const sortLabels = (a: string, b: string) => {
      if (a === "(Non renseigné)") return 1;
      if (b === "(Non renseigné)") return -1;
      return a.localeCompare(b);
    };
    return {
      rows: [...rowSet].sort(sortLabels),
      cols: [...colSet].sort(sortLabels),
      cellMap: map,
      maxFlowCount: max,
    };
  }, [cells]);

  const rowData = useMemo(
    () =>
      rows.map((row) => ({
        __row: row,
        ...Object.fromEntries(cols.map((col) => [col, cellMap.get(`${row}::${col}`)])),
      })),
    [rows, cols, cellMap],
  );

  const columnDefs = useMemo<ColDef[]>(() => {
    const rowHeaderCol: ColDef = {
      field: "__row",
      headerName: "Client \\ Serveur",
      pinned: "left",
      width: 190,
      cellStyle: { fontWeight: 600 },
      sortable: false,
      filter: false,
    };
    const zoneColumns: ColDef[] = cols.map((col) => ({
      field: col,
      headerName: col,
      width: 130,
      sortable: false,
      filter: false,
      valueFormatter: (p) => {
        const cell = p.value as MatrixCell | undefined;
        return cell && cell.flow_count > 0 ? String(cell.flow_count) : "";
      },
      tooltipValueGetter: (p) => {
        const cell = p.value as MatrixCell | undefined;
        if (!cell || cell.flow_count === 0) return undefined;
        if (colorMode === "criticality") {
          const worst = worstCriticality(cell.criticality_breakdown);
          if (!worst) return `${cell.flow_count} flux non qualifié(s)`;
          const worstCount = cell.criticality_breakdown[worst];
          return `${worstCount} flux en "${worst}" sur ${cell.flow_count} au total dans cette cellule`;
        }
        return `${cell.flow_count} flux au total`;
      },
      cellStyle: (p) => ({
        backgroundColor:
          colorMode === "volume"
            ? volumeColor((p.value as MatrixCell | undefined)?.flow_count ?? 0, maxFlowCount)
            : criticalityColor(p.value as MatrixCell | undefined),
        textAlign: "center",
        cursor: (p.value as MatrixCell | undefined)?.flow_count ? "pointer" : "default",
      }),
    }));
    return [rowHeaderCol, ...zoneColumns];
  }, [cols, colorMode, maxFlowCount]);

  const handleCellClicked = (event: CellClickedEvent) => {
    if (event.colDef.field === "__row") return;
    const cell = event.value as MatrixCell | undefined;
    if (!cell || cell.flow_count === 0) return;
    onCellClick(cell.row ?? "(Non renseigné)", cell.col ?? "(Non renseigné)");
  };

  return (
    <div style={{ height: 600, width: "100%" }}>
      <AgGridReact
        theme={themeQuartz}
        rowData={rowData}
        columnDefs={columnDefs}
        onCellClicked={handleCellClicked}
        defaultColDef={{ resizable: true }}
      />
    </div>
  );
}

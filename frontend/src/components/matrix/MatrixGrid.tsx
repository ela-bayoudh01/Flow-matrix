import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type ColDef, type CellClickedEvent } from "ag-grid-community";
import { useMemo } from "react";
import { ecartsATraiter, type CellDiffOut, type DiffStatus, type MatrixCell } from "../../api/types";
import {
  worstCriticality,
  criticalityColor as statusCriticalityColor,
  worstDiffStatus,
  displayAxisLabel,
  DIFF_STATUS_COLORS,
  DIFF_STATUS_LABELS,
  DIFF_STATUS_ORDER,
  STATUS_COLORS,
} from "../../theme/colors";
import { appGridTheme } from "../../theme/agGridTheme";

ModuleRegistry.registerModules([AllCommunityModule]);

export type ColorMode = "volume" | "debit" | "criticality" | "diff";

export const NON_QUALIFIE_COLOR = STATUS_COLORS.muted;
export const EMPTY_CELL_COLOR = "#f5f5f5"; // aucun flow entre cette paire
// Distinct de EMPTY_CELL_COLOR : n'est en réalité jamais utilisé pour le volume de données
// (total_bytes est toujours calculable, contrairement au débit) -- gardé pour le débit en
// tooltip secondaire, cf. formatBitrate/cellBitrate ci-dessous.
export const DEBIT_NA_COLOR = "#9e9e9e";

// Métrique PRINCIPALE du mode "Colorer par volume de données" : octets échangés bruts
// (total_initiator_bytes + total_responder_bytes), affichés ET utilisés pour la couleur.
// Pas flow_count (déjà la métrique du mode "volume de flux") ni un débit (voir formatBitrate
// ci-dessous, relégué en info secondaire au survol -- cf. clarification demandée par Loulou :
// volume brut et débit sont deux métriques différentes, le volume brut est la principale).
function formatByteVolume(bytes: number): string {
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

function formatBitrate(bytesPerSecond: number): string {
  if (bytesPerSecond < 1024) return `${bytesPerSecond.toFixed(0)} o/s`;
  const units = ["Ko/s", "Mo/s", "Go/s"];
  let value = bytesPerSecond / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

// null = non calculable (durée cumulée nulle) -- info secondaire uniquement (tooltip), jamais
// silencieusement 0 ou Infinity. N'entre plus dans le calcul de la couleur de cellule.
function cellBitrate(cell: MatrixCell | undefined): number | null {
  if (!cell || cell.flow_count === 0 || cell.total_duration_seconds <= 0) return null;
  return cell.total_bytes / cell.total_duration_seconds;
}

function volumeColor(flowCount: number, maxFlowCount: number): string {
  if (flowCount === 0) return EMPTY_CELL_COLOR;
  const ratio = maxFlowCount > 0 ? Math.log(flowCount + 1) / Math.log(maxFlowCount + 1) : 0;
  const lightness = 92 - ratio * 60; // presque blanc -> bleu foncé
  return `hsl(210, 70%, ${lightness}%)`;
}

function cellCriticalityColor(cell: MatrixCell | undefined): string {
  if (!cell || cell.flow_count === 0) return EMPTY_CELL_COLOR;
  const worst = worstCriticality(cell.criticality_breakdown);
  return statusCriticalityColor(worst);
}

function cellDiffColor(diff: CellDiffOut | undefined): string {
  if (!diff) return EMPTY_CELL_COLOR;
  const worst = worstDiffStatus(diff.diff_summary);
  return worst ? DIFF_STATUS_COLORS[worst] : EMPTY_CELL_COLOR;
}

function dataVolumeColor(cell: MatrixCell | undefined, maxBytes: number): string {
  if (!cell || cell.flow_count === 0) return EMPTY_CELL_COLOR;
  const ratio = maxBytes > 0 ? Math.log(cell.total_bytes + 1) / Math.log(maxBytes + 1) : 0;
  const lightness = 92 - ratio * 60; // presque blanc -> vert foncé (teinte distincte du mode volume de flux)
  return `hsl(150, 65%, ${lightness}%)`;
}

interface MatrixGridProps {
  cells: MatrixCell[];
  colorMode: ColorMode;
  // Optionnel : la Matrice Validée (données figées) n'a pas de drill-down vers les Flow en
  // direct -- afficherait des flux vivants pour une cellule qui représente un état passé,
  // trompeur. Sans onCellClick, les cellules restent consultables (tooltip) mais pas cliquables.
  onCellClick?: (row: string, col: string) => void;
  rowAxisLabel: string;
  colAxisLabel: string;
  // Rollup du Cycle de validation (GET /api/validation-cycles/cell-diff), même dimension/
  // filtres que `cells` -- fusionné ici par (row, col), jamais recalculé : uniquement utilisé
  // quand colorMode === "diff". undefined tant que le mode n'est pas actif (la requête n'est
  // déclenchée qu'à ce moment-là côté MatrixPage).
  diffCells?: CellDiffOut[];
}

export function MatrixGrid({ cells, colorMode, onCellClick, rowAxisLabel, colAxisLabel, diffCells }: MatrixGridProps) {
  const { rows, cols, cellMap, maxFlowCount, maxBytes } = useMemo(() => {
    const rowSet = new Set<string>();
    const colSet = new Set<string>();
    const map = new Map<string, MatrixCell>();
    let max = 0;
    let maxVolume = 0;
    for (const cell of cells) {
      const rowLabel = cell.row ?? "(Non renseigné)";
      const colLabel = cell.col ?? "(Non renseigné)";
      rowSet.add(rowLabel);
      colSet.add(colLabel);
      map.set(`${rowLabel}::${colLabel}`, cell);
      if (cell.flow_count > max) max = cell.flow_count;
      if (cell.total_bytes > maxVolume) maxVolume = cell.total_bytes;
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
      maxBytes: maxVolume,
    };
  }, [cells]);

  const diffCellMap = useMemo(() => {
    const map = new Map<string, CellDiffOut>();
    for (const diff of diffCells ?? []) {
      map.set(`${diff.row}::${diff.col}`, diff);
    }
    return map;
  }, [diffCells]);

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
      headerName: `${rowAxisLabel} \\ ${colAxisLabel}`,
      pinned: "left",
      width: 190,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      cellStyle: { fontWeight: 600 },
      sortable: false,
      filter: false,
    };
    const zoneColumns: ColDef[] = cols.map((col) => ({
      field: col,
      // displayAxisLabel : "Mixed" (dimension "Zone × Action") n'est jamais présentable tel
      // quel (2026-09-06) -- relabellisation d'affichage uniquement, la valeur groupée reste
      // "Mixed" (col/cellMap), jamais touchée.
      headerName: displayAxisLabel(col),
      // Ni une largeur fixe (autoSizeStrategy s'en charge, cf. <AgGridReact>) ni un texte
      // d'en-tête tronqué : deux valeurs distinctes avec un long préfixe commun (ex. deux
      // règles ACL "ACL_ANY_IN...") doivent rester visuellement distinguables sans survol
      // ni clic -- bug réel trouvé par Loulou (2026-08-13, voir docs/05-matrix-engine.md §10).
      minWidth: 90,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      headerTooltip: displayAxisLabel(col), // filet de sécurité si le texte enroulé reste ambigu malgré tout
      sortable: false,
      filter: false,
      valueFormatter: (p) => {
        const cell = p.value as MatrixCell | undefined;
        if (!cell || cell.flow_count === 0) return "";
        if (colorMode === "diff") {
          const diff = diffCellMap.get(`${p.data.__row}::${col}`);
          // 2026-09-12, bug réel corrigé : ce calcul redéfinissait "écart à traiter" en dur
          // (nouveau + modifie + disparu, donc disparu compté à tort et regle_non_appliquee
          // jamais compté) -- réutilise désormais ecartsATraiter(), seule définition, déjà
          // partagée avec ValidationCyclePage.tsx.
          const ecarts = diff ? ecartsATraiter(diff.diff_summary) : 0;
          return ecarts > 0 ? `${ecarts} écart(s)` : "conforme";
        }
        return colorMode === "debit" ? formatByteVolume(cell.total_bytes) : String(cell.flow_count);
      },
      tooltipValueGetter: (p) => {
        const cell = p.value as MatrixCell | undefined;
        if (!cell || cell.flow_count === 0) return undefined;
        if (colorMode === "criticality") {
          const worst = worstCriticality(cell.criticality_breakdown);
          if (!worst) return `${cell.flow_count} flux non qualifié(s)`;
          const worstCount = cell.criticality_breakdown[worst];
          return `${worstCount} flux en "${displayAxisLabel(worst)}" sur ${cell.flow_count} au total dans cette cellule`;
        }
        if (colorMode === "debit") {
          const bitrate = cellBitrate(cell);
          const rateText = bitrate === null ? "débit non calculable (durée cumulée nulle)" : `débit moyen ${formatBitrate(bitrate)}`;
          return `${formatByteVolume(cell.total_bytes)} sur ${cell.flow_count} flux -- ${rateText}`;
        }
        if (colorMode === "diff") {
          const diff = diffCellMap.get(`${p.data.__row}::${col}`);
          if (!diff) return "Aucune baseline pour l'instant -- tout est \"nouveau\"";
          // DIFF_STATUS_ORDER (même ordre que la couleur de cellule, worstDiffStatus
          // ci-dessus) -- 2026-09-12, bug réel corrigé : cette liste omettait
          // "regle_non_appliquee" (jamais visible dans l'infobulle), pas seulement le
          // total "écart(s)" ci-dessus.
          return DIFF_STATUS_ORDER.map(
            (status) => `${DIFF_STATUS_LABELS[status]} : ${diff.diff_summary[status as DiffStatus]}`,
          ).join(" -- ");
        }
        return `${cell.flow_count} flux au total`;
      },
      cellStyle: (p) => {
        const cell = p.value as MatrixCell | undefined;
        let backgroundColor: string;
        if (colorMode === "volume") backgroundColor = volumeColor(cell?.flow_count ?? 0, maxFlowCount);
        else if (colorMode === "debit") backgroundColor = dataVolumeColor(cell, maxBytes);
        else if (colorMode === "diff") backgroundColor = cell?.flow_count ? cellDiffColor(diffCellMap.get(`${p.data.__row}::${col}`)) : EMPTY_CELL_COLOR;
        else backgroundColor = cellCriticalityColor(cell);
        return { backgroundColor, textAlign: "center", cursor: cell?.flow_count && onCellClick ? "pointer" : "default" };
      },
    }));
    return [rowHeaderCol, ...zoneColumns];
  }, [cols, colorMode, maxFlowCount, maxBytes, rowAxisLabel, colAxisLabel, diffCellMap, onCellClick]);

  const handleCellClicked = (event: CellClickedEvent) => {
    if (!onCellClick) return;
    if (event.colDef.field === "__row") return;
    const cell = event.value as MatrixCell | undefined;
    if (!cell || cell.flow_count === 0) return;
    onCellClick(cell.row ?? "(Non renseigné)", cell.col ?? "(Non renseigné)");
  };

  return (
    <div style={{ height: 600, width: "100%" }}>
      <AgGridReact
        theme={appGridTheme}
        rowData={rowData}
        columnDefs={columnDefs}
        onCellClicked={handleCellClicked}
        defaultColDef={{ resizable: true }}
        autoSizeStrategy={{ type: "fitCellContents" }}
      />
    </div>
  );
}

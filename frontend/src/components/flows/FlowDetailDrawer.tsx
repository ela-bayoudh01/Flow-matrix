import { useMemo } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import { useFlows } from "../../hooks/useFlows";
import { useValidationCycleDiff } from "../../hooks/useValidationCycle";
import { FlowsTable, type FlowWithDiff } from "./FlowsTable";
import { FlowsSummaryBar } from "./FlowsSummaryBar";
import { TableSkeleton } from "../common/TableSkeleton";
import type { FlowFilterValues } from "../../api/types";

interface FlowDetailDrawerProps {
  open: boolean;
  onClose: () => void;
  // Dimension de matrice + valeurs de la cellule cliquée (fonctionne pour n'importe quelle
  // dimension -- "zone", "zone_port", "direction_criticality"... -- pas seulement Zone×Zone).
  dimension?: string;
  rowValue?: string;
  colValue?: string;
  // Filtres actifs sur la matrice (action, protocole, criticité...) : le drill-down doit
  // montrer exactement les flux qui ont contribué à la cellule filtrée cliquée, pas tous
  // les flux de cette cellule sans tenir compte des autres filtres actifs.
  extraFilters?: FlowFilterValues;
  // Colonne "Écart" (2026-09-12, demande de l'encadrant) -- affichée uniquement quand la
  // Matrice Réelle est en mode "Colorer par écart" (MatrixPage.tsx) : sans ça, le total de la
  // cellule (ex. 4) et le nombre d'écarts (ex. 3) ne correspondaient pas visuellement, sans
  // moyen de voir directement lequel des flux est "conforme" (donc exclu du décompte).
  // Requête séparée de useFlows ci-dessous (qui reste la source des tuiles de synthèse,
  // inchangée) -- juste de quoi décorer chaque ligne de son statut d'écart, même cellule,
  // même exclusion des flux inactifs ce cycle (voir Services/validation_cycle_engine.py::
  // compute_diff, dimension/row_value/col_value).
  showDiff?: boolean;
}

export function FlowDetailDrawer({
  open,
  onClose,
  dimension,
  rowValue,
  colValue,
  extraFilters,
  showDiff = false,
}: FlowDetailDrawerProps) {
  const canQuery = open && !!dimension && !!rowValue && !!colValue;
  const { data, isLoading } = useFlows(
    { ...extraFilters, dimension, row_value: rowValue, col_value: colValue, limit: 500 },
    { enabled: canQuery },
  );
  const { data: diffData } = useValidationCycleDiff(
    { ...extraFilters, dimension, row_value: rowValue, col_value: colValue, limit: 500 },
    { enabled: canQuery && showDiff },
  );

  const diffStatusByFlowId = useMemo(() => {
    const map = new Map<number, FlowWithDiff["diff_status"]>();
    for (const item of diffData?.items ?? []) {
      map.set(item.flow.id, item.diff_status);
    }
    return map;
  }, [diffData]);

  const flows: FlowWithDiff[] = data?.items.map((flow) => ({ ...flow, diff_status: diffStatusByFlowId.get(flow.id) })) ?? [];

  return (
    <Drawer anchor="right" open={open} onClose={onClose}>
      <Box sx={{ width: { xs: "100vw", md: 900 }, p: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
          <Typography variant="h6">
            {rowValue} → {colValue}
          </Typography>
          <IconButton onClick={onClose} aria-label="Fermer">
            <CloseIcon />
          </IconButton>
        </Box>

        {isLoading && <TableSkeleton />}
        {data && (
          <>
            <FlowsSummaryBar summary={data.summary} />
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {data.items.length} flux affiché(s) sur {data.total_count} dans cette cellule
            </Typography>
            {/* Purement consultatif (2026-09-12, demande de l'encadrant) : Valider/Bloquer/
                Changer la règle n'apparaissent plus que sur la page Cycle de validation, seul
                espace de travail pour décider quoi que ce soit sur un flux. */}
            <FlowsTable flows={flows} showDiffColumn={showDiff} readOnly />
          </>
        )}
      </Box>
    </Drawer>
  );
}

import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import { useValidatedMatrixFlowsCell } from "../../hooks/useValidationCycle";
import { FlowsTable } from "./FlowsTable";
import { FlowsSummaryBar } from "./FlowsSummaryBar";
import { TableSkeleton } from "../common/TableSkeleton";

// Drill-down d'une cellule de la Matrice Validée (2026-09-09, demande de l'encadrant) --
// même principe que FlowDetailDrawer (Matrice Réelle), mais lit FlowSnapshot du cycle
// précis affiché plutôt que Flow en direct : sinon la liste affichée ne correspondrait plus
// à ce que montre la cellule si des Flow ont changé depuis (voir
// Services/validation_cycle_engine.py::list_flow_snapshots_for_cell). En lecture seule
// (FlowsTable readOnly) -- Valider/Bloquer/Changer la règle agiraient sur le Flow vivant sans
// se refléter dans cette vue historique, trompeur (raison même du "pas de drill-down" acté le
// 2026-08-21, résolue ici en changeant de source de données plutôt qu'en l'ignorant).
interface ValidatedFlowDetailDrawerProps {
  open: boolean;
  onClose: () => void;
  cycleId?: number;
  dimension: string;
  rowValue?: string;
  colValue?: string;
}

export function ValidatedFlowDetailDrawer({ open, onClose, cycleId, dimension, rowValue, colValue }: ValidatedFlowDetailDrawerProps) {
  const canQuery = open && cycleId !== undefined && !!rowValue && !!colValue;
  const { data, isLoading } = useValidatedMatrixFlowsCell({
    cycleId: canQuery ? cycleId : undefined,
    dimension,
    rowValue: canQuery ? rowValue : undefined,
    colValue: canQuery ? colValue : undefined,
  });

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
        {/* <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          État figé de cette baseline -- Valider/Bloquer/Changer la règle indisponibles ici,
          reflète uniquement ce que ce cycle a figé, jamais l'état courant des flux.
        </Typography> */}

        {isLoading && <TableSkeleton />}
        {data && (
          <>
            <FlowsSummaryBar summary={data.summary} />
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {data.items.length} flux affiché(s) sur {data.total_count} dans cette cellule
            </Typography>
            <FlowsTable flows={data.items} readOnly />
          </>
        )}
      </Box>
    </Drawer>
  );
}

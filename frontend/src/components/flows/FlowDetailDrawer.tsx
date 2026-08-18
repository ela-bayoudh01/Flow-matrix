import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import { useFlows } from "../../hooks/useFlows";
import { FlowsTable } from "./FlowsTable";
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
}

export function FlowDetailDrawer({
  open,
  onClose,
  dimension,
  rowValue,
  colValue,
  extraFilters,
}: FlowDetailDrawerProps) {
  const canQuery = open && !!dimension && !!rowValue && !!colValue;
  const { data, isLoading } = useFlows(
    { ...extraFilters, dimension, row_value: rowValue, col_value: colValue, limit: 500 },
    { enabled: canQuery },
  );

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
            <FlowsTable flows={data.items} />
          </>
        )}
      </Box>
    </Drawer>
  );
}

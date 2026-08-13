import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import ToggleButton from "@mui/material/ToggleButton";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import { useMatrix } from "../hooks/useMatrix";
import { MatrixGrid, type ColorMode } from "../components/matrix/MatrixGrid";
import { MatrixLegend } from "../components/matrix/MatrixLegend";
import { FlowDetailDrawer } from "../components/flows/FlowDetailDrawer";
import { FilterBar } from "../components/filters/FilterBar";
import type { FlowFilterValues } from "../api/types";

export function MatrixPage() {
  const [colorMode, setColorMode] = useState<ColorMode>("volume");
  const [filters, setFilters] = useState<FlowFilterValues>({});
  const [selectedCell, setSelectedCell] = useState<{ row: string; col: string } | null>(null);
  const { data, isLoading, isError, error } = useMatrix("zone", filters);

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Matrice Zone × Zone
      </Typography>

      <FilterBar value={filters} onChange={setFilters} />

      <ToggleButtonGroup
        value={colorMode}
        exclusive
        onChange={(_, value: ColorMode | null) => value && setColorMode(value)}
        size="small"
        sx={{ mb: 2 }}
      >
        <ToggleButton value="volume">Colorer par volume de flux</ToggleButton>
        <ToggleButton value="criticality">Colorer par criticité</ToggleButton>
      </ToggleButtonGroup>

      {colorMode === "criticality" && <MatrixLegend />}

      {isLoading && <CircularProgress />}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data && data.cells.length === 0 && <Alert severity="info">Aucun flux ne correspond à ces filtres.</Alert>}

      {data && data.cells.length > 0 && (
        <MatrixGrid
          cells={data.cells}
          colorMode={colorMode}
          onCellClick={(row, col) => setSelectedCell({ row, col })}
        />
      )}

      <FlowDetailDrawer
        open={selectedCell !== null}
        onClose={() => setSelectedCell(null)}
        ingressZone={selectedCell?.row}
        egressZone={selectedCell?.col}
        extraFilters={filters}
      />
    </Box>
  );
}

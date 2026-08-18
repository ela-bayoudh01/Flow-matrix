import { useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import ToggleButton from "@mui/material/ToggleButton";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import ListSubheader from "@mui/material/ListSubheader";
import Alert from "@mui/material/Alert";
import Tooltip from "@mui/material/Tooltip";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { useMatrix } from "../hooks/useMatrix";
import { MatrixGrid, type ColorMode } from "../components/matrix/MatrixGrid";
import { MatrixLegend } from "../components/matrix/MatrixLegend";
import { FlowDetailDrawer } from "../components/flows/FlowDetailDrawer";
import { FilterBar } from "../components/filters/FilterBar";
import { TableSkeleton } from "../components/common/TableSkeleton";
import {
  MATRIX_DIMENSIONS,
  SELECTABLE_GROUPS,
  DEFAULT_MATRIX_DIMENSION,
  matrixDimensionMeta,
  unsetLabelExplanation,
} from "../components/matrix/matrixDimensions";
import type { FlowFilterValues } from "../api/types";

export function MatrixPage() {
  const [dimension, setDimension] = useState(DEFAULT_MATRIX_DIMENSION);
  const [colorMode, setColorMode] = useState<ColorMode>("volume");
  const [filters, setFilters] = useState<FlowFilterValues>({});
  const [selectedCell, setSelectedCell] = useState<{ row: string; col: string } | null>(null);
  const { data, isLoading, isError, error } = useMatrix(dimension, filters);

  const meta = matrixDimensionMeta(dimension);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Matrice {meta.label}
      </Typography>

      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 2 }}>
        <TextField
          select
          size="small"
          label="Type de matrice"
          value={dimension}
          onChange={(e) => {
            setDimension(e.target.value);
            setSelectedCell(null); // évite un drill-down avec des libellés d'axe périmés
          }}
          sx={{ minWidth: 260 }}
        >
          {SELECTABLE_GROUPS.flatMap((group) => [
            <ListSubheader key={`group-${group}`}>{group}</ListSubheader>,
            ...MATRIX_DIMENSIONS.filter((d) => d.group === group).map((d) => (
              <MenuItem key={d.key} value={d.key}>
                {d.label}
              </MenuItem>
            )),
          ])}
        </TextField>

        <Tooltip title={<span style={{ whiteSpace: "pre-line" }}>{unsetLabelExplanation(meta)}</span>}>
          <InfoOutlinedIcon fontSize="small" color="action" sx={{ cursor: "help" }} />
        </Tooltip>
      </Stack>

      <FilterBar value={filters} onChange={setFilters} />

      <ToggleButtonGroup
        value={colorMode}
        exclusive
        onChange={(_, value: ColorMode | null) => value && setColorMode(value)}
        size="small"
        sx={{ mb: 2 }}
      >
        <ToggleButton value="volume">Colorer par nombre de flux</ToggleButton>
        <ToggleButton value="debit">Colorer par volume de données</ToggleButton>
        <ToggleButton value="criticality">Colorer par criticité</ToggleButton>
      </ToggleButtonGroup>

      {colorMode === "criticality" && <MatrixLegend />}

      {isLoading && <TableSkeleton />}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data?.dimension_notice && <Alert severity="info" sx={{ mb: 2 }}>{data.dimension_notice}</Alert>}

      {data && data.cells.length === 0 && <Alert severity="info">Aucun flux ne correspond à ces filtres.</Alert>}

      {data && data.cells.length > 0 && (
        <MatrixGrid
          cells={data.cells}
          colorMode={colorMode}
          onCellClick={(row, col) => setSelectedCell({ row, col })}
          rowAxisLabel={meta.rowLabel}
          colAxisLabel={meta.colLabel}
        />
      )}

      <FlowDetailDrawer
        open={selectedCell !== null}
        onClose={() => setSelectedCell(null)}
        dimension={dimension}
        rowValue={selectedCell?.row}
        colValue={selectedCell?.col}
        extraFilters={filters}
      />
    </Box>
  );
}

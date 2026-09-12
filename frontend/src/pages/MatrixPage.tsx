import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import ToggleButton from "@mui/material/ToggleButton";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import ListSubheader from "@mui/material/ListSubheader";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { useMatrix } from "../hooks/useMatrix";
import { useValidationCycleCellDiff, useValidatedMatrix } from "../hooks/useValidationCycle";
import { useSourceOptions } from "../hooks/useSourceOptions";
import { MatrixGrid, type ColorMode } from "../components/matrix/MatrixGrid";
import { MatrixLegend } from "../components/matrix/MatrixLegend";
import { FlowDetailDrawer } from "../components/flows/FlowDetailDrawer";
import { ValidatedFlowDetailDrawer } from "../components/flows/ValidatedFlowDetailDrawer";
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

type MatrixView = "reelle" | "validee";

// "timeslot_zone" n'est pas reconstructible depuis une Matrice Validée (first_seen_at n'est
// jamais figé dans FlowSnapshot, cf. Services/validation_cycle_engine.py) -- masqué du
// sélecteur uniquement sur l'onglet "Matrice Validée", toujours disponible sur "Réelle".
const VALIDATED_EXCLUDED_DIMENSIONS = new Set(["timeslot_zone"]);

function MatrixTypeSelector({
  dimension,
  onChange,
  excluded,
}: {
  dimension: string;
  onChange: (dimension: string) => void;
  excluded?: Set<string>;
}) {
  const meta = matrixDimensionMeta(dimension);
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 2 }}>
      <TextField select size="small" label="Type de matrice" value={dimension} onChange={(e) => onChange(e.target.value)} sx={{ minWidth: 260 }}>
        {SELECTABLE_GROUPS.flatMap((group) => {
          const dims = MATRIX_DIMENSIONS.filter((d) => d.group === group && !excluded?.has(d.key));
          if (dims.length === 0) return [];
          return [
            <ListSubheader key={`group-${group}`}>{group}</ListSubheader>,
            ...dims.map((d) => (
              <MenuItem key={d.key} value={d.key}>
                {d.label}
              </MenuItem>
            )),
          ];
        })}
      </TextField>
      <Tooltip title={<span style={{ whiteSpace: "pre-line" }}>{unsetLabelExplanation(meta)}</span>}>
        <InfoOutlinedIcon fontSize="small" color="action" sx={{ cursor: "help" }} />
      </Tooltip>
    </Stack>
  );
}

export function MatrixPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<MatrixView>("reelle");
  const [dimension, setDimension] = useState(DEFAULT_MATRIX_DIMENSION);
  const [colorMode, setColorMode] = useState<ColorMode>("volume");
  const [filters, setFilters] = useState<FlowFilterValues>({});
  const [selectedCell, setSelectedCell] = useState<{ row: string; col: string } | null>(null);
  const sourceOptions = useSourceOptions();
  const [validatedSource, setValidatedSource] = useState<string>("");
  // Drill-down d'une cellule de la Matrice Validée (2026-09-09, demande de l'encadrant).
  const [selectedValidatedCell, setSelectedValidatedCell] = useState<{ row: string; col: string } | null>(null);

  useEffect(() => {
    if (!validatedSource && sourceOptions.length > 0) setValidatedSource(sourceOptions[0]);
  }, [validatedSource, sourceOptions]);

  // "Colorer par écart" n'a de sens que sur la Matrice Réelle (compare à la Matrice
  // Validée) -- si on quitte cet onglet dessus, retombe sur "volume" pour ne pas laisser un
  // mode orphelin sur l'onglet Validée (qui n'a que 3 modes, sans diff).
  useEffect(() => {
    if (view === "validee" && colorMode === "diff") setColorMode("volume");
  }, [view, colorMode]);
  // Source obligatoire pour "Colorer par écart" (2026-09-12, demande de l'encadrant) -- même
  // principe que le reste de la page (Cycle de validation/Matrice Validée, toujours propres à
  // une source). Avant ce garde-fou, le mode mélangeait les flux de toutes les sources --
  // bug réel signalé en testant un réimport : le calcul "écart(s)" par cellule (cf.
  // MatrixGrid.tsx, corrigé au même moment) devenait trivialement ~égal au nombre de flux.
  // Repli automatique sur "volume" si la source est effacée pendant que le mode est actif.
  useEffect(() => {
    if (colorMode === "diff" && !filters.source) setColorMode("volume");
  }, [colorMode, filters.source]);
  useEffect(() => {
    if (view === "validee" && VALIDATED_EXCLUDED_DIMENSIONS.has(dimension)) setDimension(DEFAULT_MATRIX_DIMENSION);
  }, [view, dimension]);

  const { data, isLoading, isError, error } = useMatrix(dimension, filters);
  const { data: diffData } = useValidationCycleCellDiff(dimension, filters, view === "reelle" && colorMode === "diff" && !!filters.source);
  const { data: validatedData, isLoading: isValidatedLoading, isError: isValidatedError, error: validatedError } = useValidatedMatrix(
    view === "validee" ? validatedSource : "",
    dimension,
  );

  const meta = matrixDimensionMeta(dimension);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 1 }}>
        Matrice {meta.label}
      </Typography>

      <Tabs value={view} onChange={(_, v: MatrixView) => setView(v)} sx={{ mb: 2 }}>
        <Tab value="reelle" label="Matrice Réelle" />
        <Tab value="validee" label="Matrice Validée" />
      </Tabs>

      {view === "reelle" && (
        <>
          <MatrixTypeSelector dimension={dimension} onChange={(d) => { setDimension(d); setSelectedCell(null); }} />

          <FilterBar value={filters} onChange={setFilters} />

          <ToggleButtonGroup value={colorMode} exclusive onChange={(_, value: ColorMode | null) => value && setColorMode(value)} size="small" sx={{ mb: 2 }}>
            <ToggleButton value="volume">Colorer par nombre de flux</ToggleButton>
            <ToggleButton value="debit">Colorer par volume de données</ToggleButton>
            <ToggleButton value="criticality">Colorer par criticité</ToggleButton>
            {/* Désactivé sans source (2026-09-12, demande de l'encadrant) : un cycle de
                validation est toujours propre à une source, comme le reste de la page
                (Cycle de validation/Matrice Validée) -- empêche de le sélectionner plutôt
                que d'afficher un résultat mélangeant toutes les sources. */}
            <Tooltip title={filters.source ? "" : "Choisis d'abord une source (un cycle de validation est toujours propre à une source)."}>
              <span>
                <ToggleButton value="diff" disabled={!filters.source}>
                  Colorer par écart (vs Matrice Validée)
                </ToggleButton>
              </span>
            </Tooltip>
          </ToggleButtonGroup>

          {colorMode === "criticality" && <MatrixLegend />}
          {colorMode === "diff" && filters.source && !diffData?.cycles[filters.source] && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Aucune Matrice Validée pour l'instant sur {filters.source} -- toutes les cellules
              non vides sont considérées "nouveau". Clôture un premier cycle depuis la page
              Cycle de validation pour obtenir une vraie comparaison.
            </Alert>
          )}

          {/* Précision permanente (2026-09-12, demande de l'encadrant) -- la Matrice Réelle
              est désormais scopée au cycle courant (Services/matrix_engine.py::build_matrix,
              corrigé après un bug de conception réel découvert en testant un réimport) :
              flow_count représente les flux ACTIFS ce cycle, pas tout l'historique jamais
              connu -- celui-ci reste consultable, lui, dans la Table des flux (comportement
              lifetime inchangé). */}
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
            Cette matrice ne montre que les flux actifs dans le cycle courant (retouchés depuis
            la dernière clôture, ou jamais clôturés pour l'instant) -- pas l'historique complet
            jamais connu, toujours consultable dans la Table des flux.
          </Typography>

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
              diffCells={diffData?.cells}
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
        </>
      )}

      {view === "validee" && (
        <>
          <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 1, flexWrap: "wrap" }}>
            <TextField
              select
              size="small"
              label="Source (firewall)"
              value={validatedSource}
              onChange={(e) => {
                setValidatedSource(e.target.value);
                setSelectedValidatedCell(null);
              }}
              sx={{ minWidth: 220 }}
            >
              {sourceOptions.map((s) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </TextField>
            <Button size="small" onClick={() => navigate("/validation-cycle")}>
              Aller au Cycle de validation
            </Button>
          </Stack>

          <MatrixTypeSelector
            dimension={dimension}
            onChange={(d) => { setDimension(d); setSelectedValidatedCell(null); }}
            excluded={VALIDATED_EXCLUDED_DIMENSIONS}
          />

          <ToggleButtonGroup value={colorMode === "diff" ? "volume" : colorMode} exclusive onChange={(_, value: ColorMode | null) => value && setColorMode(value)} size="small" sx={{ mb: 2 }}>
            <ToggleButton value="volume">Colorer par nombre de flux</ToggleButton>
            <ToggleButton value="debit">Colorer par volume de données</ToggleButton>
            <ToggleButton value="criticality">Colorer par criticité</ToggleButton>
          </ToggleButtonGroup>

          {colorMode === "criticality" && <MatrixLegend />}

          {!validatedSource && sourceOptions.length === 0 && (
            <Alert severity="info">Aucune source connue! importe d'abord un log pour voir apparaître une Matrice Validée.</Alert>
          )}

          {validatedSource && validatedData && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {validatedData.cycle
                ? `Matrice Validée de ${validatedSource} : instantané figé le ${new Date(validatedData.cycle.closed_at).toLocaleString("fr-FR")}${validatedData.cycle.closed_by ? ` par ${validatedData.cycle.closed_by}` : ""} -- ${validatedData.cycle.flow_count} flux. Sert de référence pour le prochain log de cette source.`
                : `Aucune Matrice Validée pour l'instant sur ${validatedSource} ,clôture un premier cycle depuis la page Cycle de validation.`}
            </Typography>
          )}

          {isValidatedLoading && <TableSkeleton />}
          {isValidatedError && <Alert severity="error">{(validatedError as Error).message}</Alert>}

          {validatedData && validatedData.cells.length === 0 && validatedData.cycle && (
            <Alert severity="info">Ce cycle ne contenait aucun flux pour cette dimension.</Alert>
          )}

          {validatedData && validatedData.cells.length > 0 && (
            <MatrixGrid
              cells={validatedData.cells}
              colorMode={colorMode === "diff" ? "volume" : colorMode}
              onCellClick={(row, col) => setSelectedValidatedCell({ row, col })}
              rowAxisLabel={meta.rowLabel}
              colAxisLabel={meta.colLabel}
            />
          )}

          <ValidatedFlowDetailDrawer
            open={selectedValidatedCell !== null}
            onClose={() => setSelectedValidatedCell(null)}
            cycleId={validatedData?.cycle?.id}
            dimension={dimension}
            rowValue={selectedValidatedCell?.row}
            colValue={selectedValidatedCell?.col}
          />
        </>
      )}
    </Box>
  );
}

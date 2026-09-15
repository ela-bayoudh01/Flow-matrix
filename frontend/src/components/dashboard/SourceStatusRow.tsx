import Chip from "@mui/material/Chip";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import { useValidationCycles, useValidationCycleDiff } from "../../hooks/useValidationCycle";
import { useSourceCoverageFor } from "../../hooks/useSourceCoverage";
import { STATUS_COLORS } from "../../theme/colors";
import { ecartsATraiter } from "../../api/types";

// Ligne de la section "État des sources" du Dashboard (2026-09-12, demande de l'encadrant) --
// réutilise le calcul de diff DÉJÀ EXISTANT (Services/validation_cycle_engine.py::compute_diff,
// même résumé que les StatTiles de ValidationCyclePage.tsx) : aucune nouvelle logique de calcul,
// juste un affichage compact supplémentaire de ce qui existe déjà.
//
// Précédence de l'état (dans cet ordre, jamais l'inverse) :
//   1. "Premier cycle" si AUCUN ValidationCycle n'existe encore pour cette source -- sinon
//      compute_diff() considérerait tout comme "nouveau" faute de baseline, ce qui afficherait
//      à tort "N écart(s)" avant même la première clôture (rien à "corriger" à ce stade).
//   2. "Conforme" si ecartsATraiter() (nouveau + modifie + regle_non_appliquee, seule
//      définition du projet) vaut 0.
//   3. "{N} écart(s)" sinon.
export function SourceStatusRow({ source }: { source: string }) {
  const coverage = useSourceCoverageFor(source);
  const { data: cycles } = useValidationCycles(source, 1);
  const { data: diffData } = useValidationCycleDiff({ source, limit: 1 });

  const lastCycle = cycles?.items[0];
  const hasCycle = (cycles?.total_count ?? 0) > 0;
  const gapCount = diffData ? ecartsATraiter(diffData.summary) : 0;

  let stateLabel = "…";
  let stateColor: string = STATUS_COLORS.muted;
  if (cycles && diffData) {
    if (!hasCycle) {
      stateLabel = "Premier cycle";
      stateColor = STATUS_COLORS.muted;
    } else if (gapCount === 0) {
      stateLabel = "Conforme";
      stateColor = STATUS_COLORS.good;
    } else {
      stateLabel = `${gapCount} écart(s)`;
      stateColor = STATUS_COLORS.serious;
    }
  }

  return (
    <TableRow>
      <TableCell>{source}</TableCell>
      <TableCell>{coverage?.last_imported_at ? new Date(coverage.last_imported_at).toLocaleString("fr-FR") : "—"}</TableCell>
      <TableCell>{lastCycle ? new Date(lastCycle.closed_at).toLocaleString("fr-FR") : "—"}</TableCell>
      <TableCell>
        <Chip size="small" label={stateLabel} sx={{ backgroundColor: stateColor, color: "#fff" }} />
      </TableCell>
    </TableRow>
  );
}

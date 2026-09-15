import Typography from "@mui/material/Typography";
import type { SourceCoverageOut } from "../../api/types";

// Ligne d'indication temporelle par source (2026-09-12, demande de l'encadrant après démo) --
// réutilisée telle quelle par MatrixPage.tsx et FlowsTablePage.tsx (Services/flows_query.py::
// list_source_coverage, une seule requête, cf. useSourceCoverage.ts). `coverage` undefined
// (source pas encore choisie, ou pas encore chargée) -> rien affiché, jamais une ligne vide.
export function SourceCoverageNote({ coverage }: { coverage: SourceCoverageOut | undefined }) {
  if (!coverage) return null;
  return (
    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
      Période couverte : {coverage.first_seen_at ? new Date(coverage.first_seen_at).toLocaleString("fr-FR") : "—"}
      {" → "}
      {coverage.last_seen_at ? new Date(coverage.last_seen_at).toLocaleString("fr-FR") : "—"}
      {coverage.last_imported_at && ` -- dernier import le ${new Date(coverage.last_imported_at).toLocaleString("fr-FR")}`}.
    </Typography>
  );
}

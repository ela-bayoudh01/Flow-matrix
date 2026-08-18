import { themeQuartz } from "ag-grid-community";
import { IDENTITY_COLORS } from "./colors";

// Thème AG Grid partagé par les 5 tableaux de l'application (Matrice, FlowsTable,
// RecommendationsTable, AclProposalsTable, HistoryPage) -- avant cette étape chacun utilisait
// `themeQuartz` brut sans configuration, donc un style légèrement différent d'un tableau à
// l'autre (mêmes défauts, mais aucune garantie de rester synchronisés). Alternance de lignes
// + surbrillance au survol, cohérentes avec la palette du thème MUI (theme/colors.ts).
export const appGridTheme = themeQuartz.withParams({
  headerFontWeight: 600,
  headerBackgroundColor: "#f9f9f7",
  oddRowBackgroundColor: "#f9f9f7",
  rowHoverColor: "rgba(42,120,214,0.06)",
  borderColor: "rgba(11,11,11,0.10)",
  wrapperBorderRadius: 8,
  accentColor: IDENTITY_COLORS.blue,
  fontFamily: '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif',
});

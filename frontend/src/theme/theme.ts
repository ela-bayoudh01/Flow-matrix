import { createTheme } from "@mui/material/styles";
import { IDENTITY_COLORS, STATUS_COLORS } from "./colors";

// Thème personnalisé -- avant cette étape, `createTheme()` sans argument (couleurs/typo MUI
// par défaut). Palette calée sur theme/colors.ts (méthode data-viz du projet), formes/ombres
// réduites au profit de bordures fines pour un rendu plus proche d'un outil professionnel
// (Linear/Notion/Datadog) que du Material Design par défaut.
export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: IDENTITY_COLORS.blue },
    secondary: { main: "#383835" },
    error: { main: STATUS_COLORS.critical },
    warning: { main: STATUS_COLORS.warning },
    success: { main: STATUS_COLORS.good },
    background: {
      default: "#f9f9f7", // plan de page
      paper: "#fcfcfb", // cartes/tableaux
    },
    text: {
      primary: "#0b0b0b",
      secondary: "#52514e",
    },
    divider: "rgba(11,11,11,0.10)",
  },
  shape: {
    borderRadius: 8,
  },
  typography: {
    fontFamily: '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif',
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" },
        outlined: { borderColor: "rgba(11,11,11,0.10)" },
      },
      defaultProps: { elevation: 0 },
    },
    MuiAppBar: {
      styleOverrides: {
        root: { boxShadow: "none", borderBottom: "1px solid rgba(11,11,11,0.10)" },
      },
      defaultProps: { elevation: 0 },
    },
    MuiCard: {
      styleOverrides: {
        root: { border: "1px solid rgba(11,11,11,0.10)", boxShadow: "none" },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8 },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 600 },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          "&:hover": { backgroundColor: "rgba(42,120,214,0.06)" },
        },
      },
    },
  },
});

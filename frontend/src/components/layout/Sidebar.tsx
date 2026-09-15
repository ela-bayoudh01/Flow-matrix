import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import SpaceDashboardOutlinedIcon from "@mui/icons-material/SpaceDashboardOutlined";
import CloudUploadOutlinedIcon from "@mui/icons-material/CloudUploadOutlined";
import GridViewOutlinedIcon from "@mui/icons-material/GridViewOutlined";
import ListAltOutlinedIcon from "@mui/icons-material/ListAltOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import CompareArrowsOutlinedIcon from "@mui/icons-material/CompareArrowsOutlined";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";

// "Recommandations" et "Propositions ACL" retirées de la navigation le 2026-09-03, demande
// de l'encadrant après démo (pas jugées utiles pour l'instant, on se concentre sur Matrice +
// Cycle de validation) -- AUCUN code/endpoint/modèle/test supprimé, les deux pages restent
// pleinement fonctionnelles via leurs routes directes (/recommendations, /acl-proposals,
// cf. App.tsx) pour une réactivation immédiate si le besoin revient : juste ces deux lignes
// à restaurer ici (imports RuleOutlinedIcon/TipsAndUpdatesOutlinedIcon et entrées NAV_ITEMS).
//
// "Politiques de sous-réseau" retirée à son tour le 2026-09-11 (même principe : demande de
// l'encadrant après démo) -- fusionnée dans "Cycle de validation" (tableau par sous-réseau +
// formulaire de création + politiques enregistrées, cf. ValidationCyclePage.tsx). Page,
// composants, endpoints, tests intacts, route directe (/network-policies) toujours
// fonctionnelle -- juste cette ligne à restaurer ici (import LanOutlinedIcon en plus) si le
// besoin d'une page séparée revient.
// Ordre chronologique du scénario d'utilisation réel (2026-09-12, demande de l'encadrant
// après démo) : Dashboard (vue d'ensemble) -> Import (faire entrer des logs) -> Matrice
// (explorer) -> Cycle de validation (décider) -> Table des flux (lister/consulter) ->
// Historique des validations (revoir ce qui a été décidé) -- plus l'ordre de construction
// historique du projet, qui ne reflétait pas la logique d'usage.
const NAV_ITEMS = [
  { label: "Dashboard", to: "/dashboard", icon: SpaceDashboardOutlinedIcon },
  { label: "Import", to: "/import", icon: CloudUploadOutlinedIcon },
  { label: "Matrice", to: "/matrix", icon: GridViewOutlinedIcon },
  { label: "Cycle de validation", to: "/validation-cycle", icon: CompareArrowsOutlinedIcon },
  { label: "Table des flux", to: "/flows", icon: ListAltOutlinedIcon },
  // "Historique" renommé "Historique des validations" (2026-09-12, demande de l'encadrant) --
  // ambigu seul ("historique de quoi ?") pour qui découvre l'outil ; cohérent avec le titre
  // déjà affiché en haut de HistoryPage.tsx.
  { label: "Historique des validations", to: "/history", icon: HistoryOutlinedIcon },
];

const STORAGE_KEY = "sidebar-collapsed";
const EXPANDED_WIDTH = 220;
const COLLAPSED_WIDTH = 64;

function readInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function Sidebar() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(readInitialCollapsed);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    } catch {
      // stockage indisponible (navigation privée...) -- pas bloquant, juste pas persisté
    }
  }

  const width = collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH;

  return (
    <Box
      component="nav"
      sx={{
        width,
        flexShrink: 0,
        height: "100vh",
        position: "sticky",
        top: 0,
        borderRight: "1px solid",
        borderColor: "divider",
        backgroundColor: "background.paper",
        display: "flex",
        flexDirection: "column",
        transition: (t) => t.transitions.create("width", { duration: t.transitions.duration.shorter }),
        overflowX: "hidden",
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", px: 2, py: 2.5, minHeight: 40 }}>
        <HubOutlinedIcon color="primary" />
        {!collapsed && (
          <Typography variant="subtitle1" noWrap sx={{ fontWeight: 700 }}>
            Flow Guard
          </Typography>
        )}
      </Stack>

      <Stack component="ul" sx={{ listStyle: "none", m: 0, p: 1, gap: 0.5, flex: 1 }}>
        {NAV_ITEMS.map((item) => {
          const active = location.pathname === item.to;
          const Icon = item.icon;
          const link = (
            <Box
              component={Link}
              to={item.to}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1.5,
                px: 1.5,
                py: 1,
                borderRadius: 1,
                textDecoration: "none",
                color: active ? "primary.main" : "text.secondary",
                backgroundColor: active ? "rgba(42,120,214,0.10)" : "transparent",
                borderLeft: "3px solid",
                borderLeftColor: active ? "primary.main" : "transparent",
                transition: (t) => t.transitions.create(["background-color", "color"], { duration: t.transitions.duration.shortest }),
                "&:hover": { backgroundColor: active ? "rgba(42,120,214,0.14)" : "action.hover" },
              }}
            >
              <Icon fontSize="small" />
              {!collapsed && (
                <Typography variant="body2" noWrap sx={{ fontWeight: active ? 600 : 500 }}>
                  {item.label}
                </Typography>
              )}
            </Box>
          );
          return (
            <li key={item.to}>
              {/* Infobulle systématique, pas seulement en mode replié (2026-09-12, demande de
                  l'encadrant) : même déplié, un libellé long ("Historique des validations")
                  peut être tronqué par la largeur fixe de la barre (noWrap ci-dessus) --
                  l'infobulle reste le seul moyen fiable de voir le libellé complet dans les
                  deux cas, et devient la seule indication du tout en mode replié (icônes
                  seules). */}
              <Tooltip title={item.label} placement="right">
                {link}
              </Tooltip>
            </li>
          );
        })}
      </Stack>

      <Box sx={{ p: 1, borderTop: "1px solid", borderColor: "divider" }}>
        <IconButton onClick={toggle} size="small" aria-label={collapsed ? "Déplier la navigation" : "Replier la navigation"}>
          {collapsed ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
        </IconButton>
      </Box>
    </Box>
  );
}

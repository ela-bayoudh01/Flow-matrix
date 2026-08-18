import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import SpaceDashboardOutlinedIcon from "@mui/icons-material/SpaceDashboardOutlined";
import GridViewOutlinedIcon from "@mui/icons-material/GridViewOutlined";
import ListAltOutlinedIcon from "@mui/icons-material/ListAltOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import TipsAndUpdatesOutlinedIcon from "@mui/icons-material/TipsAndUpdatesOutlined";
import RuleOutlinedIcon from "@mui/icons-material/RuleOutlined";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";

const NAV_ITEMS = [
  { label: "Dashboard", to: "/dashboard", icon: SpaceDashboardOutlinedIcon },
  { label: "Matrice", to: "/matrix", icon: GridViewOutlinedIcon },
  { label: "Table des flux", to: "/flows", icon: ListAltOutlinedIcon },
  { label: "Historique", to: "/history", icon: HistoryOutlinedIcon },
  { label: "Recommandations", to: "/recommendations", icon: TipsAndUpdatesOutlinedIcon },
  { label: "Propositions ACL", to: "/acl-proposals", icon: RuleOutlinedIcon },
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
              {collapsed ? (
                <Tooltip title={item.label} placement="right">
                  {link}
                </Tooltip>
              ) : (
                link
              )}
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

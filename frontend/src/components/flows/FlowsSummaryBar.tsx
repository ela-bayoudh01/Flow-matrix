import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import BlockOutlinedIcon from "@mui/icons-material/BlockOutlined";
import DeviceHubOutlinedIcon from "@mui/icons-material/DeviceHubOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import type { SvgIconComponent } from "@mui/icons-material";
import type { FlowsSummary } from "../../api/types";
import { STATUS_COLORS, criticalityColor, displayAxisLabel } from "../../theme/colors";

// Carte de stat partagée : Dashboard, FlowsTablePage et le panneau de détail d'une cellule
// de matrice utilisent toutes la même -- un changement ici se répercute partout, jamais
// réinventée page par page (cf. demande explicite de cohérence entre les 7 pages).
export function StatTile({
  label,
  value,
  icon: Icon,
  color,
  onClick,
}: {
  label: string;
  value: number | string;
  icon?: SvgIconComponent;
  color?: string;
  // Point d'entrée vers une vue filtrée (2026-09-10, demande de l'encadrant -- tuile
  // Dashboard "Règles non appliquées") -- optionnel, la tuile reste un simple affichage sinon.
  onClick?: () => void;
}) {
  return (
    <Card
      variant="outlined"
      onClick={onClick}
      sx={{ minWidth: 150, borderLeft: color ? `3px solid ${color}` : undefined, cursor: onClick ? "pointer" : "default" }}
    >
      <CardContent sx={{ display: "flex", alignItems: "center", gap: 1.5, "&:last-child": { pb: 2 } }}>
        {Icon && (
          <Box sx={{ display: "flex", color: color ?? "text.secondary" }}>
            <Icon fontSize="medium" />
          </Box>
        )}
        <Box>
          <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1.2, display: "block" }}>
            {label}
          </Typography>
          <Typography variant="h5" sx={{ color: color ?? "text.primary" }}>
            {value}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

export function FlowsSummaryBar({ summary }: { summary: FlowsSummary }) {
  return (
    <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: "wrap" }}>
      <StatTile label="Total flux" value={summary.total_flows} icon={DeviceHubOutlinedIcon} />
      <StatTile label="Autorisé" value={summary.allow_count} icon={CheckCircleOutlineIcon} color={STATUS_COLORS.good} />
      <StatTile label="Bloqué" value={summary.block_count} icon={BlockOutlinedIcon} color={STATUS_COLORS.critical} />
      {Object.entries(summary.criticality_breakdown).map(([label, count]) => (
        <StatTile
          key={label}
          label={`Criticité : ${displayAxisLabel(label)}`}
          value={count}
          icon={WarningAmberOutlinedIcon}
          color={criticalityColor(label === "non_qualifie" ? null : label)}
        />
      ))}
    </Stack>
  );
}

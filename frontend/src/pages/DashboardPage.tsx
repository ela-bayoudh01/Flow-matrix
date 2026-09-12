import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Skeleton from "@mui/material/Skeleton";
import DeviceHubOutlinedIcon from "@mui/icons-material/DeviceHubOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import BlockOutlinedIcon from "@mui/icons-material/BlockOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import GppMaybeOutlinedIcon from "@mui/icons-material/GppMaybeOutlined";
import { useNavigate } from "react-router-dom";
import { PieChart } from "@mui/x-charts/PieChart";
import { BarChart } from "@mui/x-charts/BarChart";
import { useFlows } from "../hooks/useFlows";
import { useValidationCycleDiff } from "../hooks/useValidationCycle";
import { StatTile } from "../components/flows/FlowsSummaryBar";
import { CRITICALITY_ORDER, STATUS_COLORS, DIFF_STATUS_COLORS, criticalityColor } from "../theme/colors";

export function DashboardPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useFlows({ limit: 1 });
  // Tuile "Règles non appliquées (toutes sources)" (2026-09-10, demande de l'encadrant,
  // remplace la réintégration de l'ancien module ACL Proposition) -- aucun filtre source :
  // compute_diff() somme déjà regle_non_appliquee sur TOUTES les sources présentes en base,
  // aucune logique d'agrégation supplémentaire nécessaire côté frontend.
  const { data: diffData } = useValidationCycleDiff({ limit: 1 });

  const criticalityData = CRITICALITY_ORDER.filter((label) => (data?.summary.criticality_breakdown[label] ?? 0) > 0).map(
    (label) => ({
      label,
      value: data!.summary.criticality_breakdown[label],
      color: criticalityColor(label),
    }),
  );

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 3 }}>
        Dashboard
      </Typography>

      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {isLoading && (
        <Stack direction="row" spacing={2} sx={{ mb: 3 }}>
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} variant="rounded" width={150} height={72} />
          ))}
        </Stack>
      )}

      {data && (
        <Stack direction="row" spacing={2} sx={{ mb: 3, flexWrap: "wrap" }}>
          <StatTile label="Total flux" value={data.summary.total_flows} icon={DeviceHubOutlinedIcon} />
          <StatTile label="Allow" value={data.summary.allow_count} icon={CheckCircleOutlineIcon} color={STATUS_COLORS.good} />
          <StatTile label="Block" value={data.summary.block_count} icon={BlockOutlinedIcon} color={STATUS_COLORS.critical} />
          {diffData && diffData.summary.regle_non_appliquee > 0 && (
            <StatTile
              label="Règles non appliquées en attente (toutes sources)"
              value={diffData.summary.regle_non_appliquee}
              icon={GppMaybeOutlinedIcon}
              color={DIFF_STATUS_COLORS.regle_non_appliquee}
              onClick={() => navigate("/validation-cycle?diff_status=regle_non_appliquee")}
            />
          )}
          {CRITICALITY_ORDER.map((label) => {
            const count = data.summary.criticality_breakdown[label];
            if (!count) return null;
            return (
              <StatTile
                key={label}
                label={`Criticité : ${label}`}
                value={count}
                icon={WarningAmberOutlinedIcon}
                color={criticalityColor(label)}
              />
            );
          })}
        </Stack>
      )}

      {data && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Répartition Allow / Block
                </Typography>
                <PieChart
                  series={[
                    {
                      data: [
                        { id: "allow", value: data.summary.allow_count, label: "Allow", color: STATUS_COLORS.good },
                        { id: "block", value: data.summary.block_count, label: "Block", color: STATUS_COLORS.critical },
                      ],
                      innerRadius: 50,
                      paddingAngle: 2,
                      cornerRadius: 3,
                    },
                  ]}
                  height={240}
                />
              </CardContent>
            </Card>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Répartition par criticité
                </Typography>
                <BarChart
                  xAxis={[{ scaleType: "band", data: criticalityData.map((d) => d.label) }]}
                  // Échelle log essayée puis abandonnée (voir docs/frontend/09-design-system.md) :
                  // en plus d'être trompeuse pour un public non expert (31 247 ne paraîtrait
                  // "que" ~3x plus haut que 6, alors que l'écart réel est ~5000x), le rendu de
                  // cette version de MUI X Charts casse carrément avec des séries à valeurs
                  // `null` mêlées à une seule valeur réelle. Solution retenue : échelle linéaire
                  // (jamais de distorsion de grandeur) + `minBarSize` (hauteur plancher en
                  // pixels, jamais 0 même pour une valeur minuscule) + label de valeur toujours
                  // affiché -- "high"/"medium" restent identifiables et lisibles sans mentir sur
                  // le fait que "low" domine réellement à ce point.
                  //
                  // Une série PAR criticité (pas une seule série multi-couleurs) : MUI X Charts
                  // n'applique une couleur par barre que via des séries séparées -- chaque
                  // série ne porte de valeur qu'à sa propre position, `null` ailleurs. Couleurs
                  // = mêmes tokens que les cartes de stats juste au-dessus et que la légende de
                  // criticité partout ailleurs dans l'app (theme/colors.ts).
                  series={criticalityData.map((d, i) => ({
                    label: d.label,
                    data: criticalityData.map((_, j) => (i === j ? d.value : null)),
                    color: d.color,
                    minBarSize: 10,
                    valueFormatter: (v: number | null) => (v === null ? "" : String(v)),
                    barLabel: "value" as const,
                  }))}
                  hideLegend
                  height={240}
                />
                
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
}

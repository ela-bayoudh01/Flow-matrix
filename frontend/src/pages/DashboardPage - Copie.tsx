import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import Skeleton from "@mui/material/Skeleton";
import DeviceHubOutlinedIcon from "@mui/icons-material/DeviceHubOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import BlockOutlinedIcon from "@mui/icons-material/BlockOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import { PieChart } from "@mui/x-charts/PieChart";
import { BarChart } from "@mui/x-charts/BarChart";
import { useFlows } from "../hooks/useFlows";
import { useRecommendations } from "../hooks/useRecommendations";
import { useAclProposals } from "../hooks/useAclProposals";
import { StatTile } from "../components/flows/FlowsSummaryBar";
import { CRITICALITY_ORDER, STATUS_COLORS, criticalityColor, FINDING_TYPE_LABELS, FINDING_TYPE_COLORS, INTENT_LABELS, INTENT_COLORS } from "../theme/colors";

function SectionSkeleton() {
  return (
    <Stack spacing={1}>
      <Skeleton variant="rounded" height={32} />
      <Skeleton variant="rounded" height={32} />
      <Skeleton variant="rounded" height={32} />
    </Stack>
  );
}

export function DashboardPage() {
  const { data, isLoading, isError, error } = useFlows({ limit: 1 });
  const { data: recommendations, isLoading: recoLoading } = useRecommendations({ status: "pending" });
  const { data: proposals, isLoading: proposalsLoading } = useAclProposals({ status: "pending" });

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
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                  Échelle linéaire -- hauteur minimale garantie pour les faibles valeurs (jamais une barre invisible), valeur exacte toujours affichée.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
                Recommandations en attente
              </Typography>
              {recoLoading && <SectionSkeleton />}
              {recommendations && recommendations.items.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  Aucune recommandation en attente.
                </Typography>
              )}
              <Stack spacing={1}>
                {recommendations?.items.slice(0, 5).map((r) => (
                  <Stack key={r.id} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <Chip
                      size="small"
                      label={FINDING_TYPE_LABELS[r.finding_type] ?? r.finding_type}
                      sx={{ backgroundColor: FINDING_TYPE_COLORS[r.finding_type] ?? "#9e9e9e", color: "#fff" }}
                    />
                    <Typography variant="body2" noWrap>
                      {r.source} -- {r.rule_name !== "(Aucune règle ciblée)" ? r.rule_name : `${r.ingress_zone} → ${r.egress_zone}`}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
                Propositions ACL en attente
              </Typography>
              {proposalsLoading && <SectionSkeleton />}
              {proposals && proposals.items.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  Aucune proposition en attente.
                </Typography>
              )}
              <Stack spacing={1}>
                {proposals?.items.slice(0, 5).map((p) => (
                  <Stack key={p.id} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <Chip
                      size="small"
                      label={INTENT_LABELS[p.intent] ?? p.intent}
                      sx={{ backgroundColor: INTENT_COLORS[p.intent] ?? "#9e9e9e", color: "#fff" }}
                    />
                    <Typography variant="body2" noWrap>
                      {p.source} -- {p.suggested_rule_name}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}

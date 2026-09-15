import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Skeleton from "@mui/material/Skeleton";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
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
import { useSourceOptions } from "../hooks/useSourceOptions";
import { StatTile } from "../components/flows/FlowsSummaryBar";
import { SourceDashboardCard } from "../components/dashboard/SourceDashboardCard";
import { SourceStatusRow } from "../components/dashboard/SourceStatusRow";
import { CRITICALITY_ORDER, STATUS_COLORS, DIFF_STATUS_COLORS, criticalityColor, displayAxisLabel } from "../theme/colors";

export function DashboardPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useFlows({ limit: 1 });
  // Répartition par source (2026-09-12, demande de l'encadrant après démo) -- liste dérivée
  // dynamiquement, jamais codée en dur (même principe que partout ailleurs dans l'app).
  const sourceOptions = useSourceOptions();
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

      {/* Refonte (2026-09-12, demande de l'encadrant après démo) : vue d'ensemble globale
          d'abord (tuiles + graphiques déjà existants, inchangés dans leur contenu -- juste
          requalifiés "toutes sources"), puis répartition claire par firewall plus bas. */}
      <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
        Vue d'ensemble
      </Typography>

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
          <StatTile label="Autorisé" value={data.summary.allow_count} icon={CheckCircleOutlineIcon} color={STATUS_COLORS.good} />
          <StatTile label="Bloqué" value={data.summary.block_count} icon={BlockOutlinedIcon} color={STATUS_COLORS.critical} />
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
                label={`Criticité : ${displayAxisLabel(label)}`}
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
                        { id: "allow", value: data.summary.allow_count, label: "Autorisé", color: STATUS_COLORS.good },
                        { id: "block", value: data.summary.block_count, label: "Bloqué", color: STATUS_COLORS.critical },
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
                  layout="horizontal"
                  // Barres HORIZONTALES (2026-09-12, demande de l'encadrant) -- remplace la
                  // version verticale : "low" écrasait visuellement medium/high/critical au
                  // point de les rendre quasi invisibles. En horizontal, chaque catégorie
                  // garde sa PROPRE ligne à hauteur fixe (`categoryGapRatio`), donc son
                  // étiquette et sa valeur restent toujours lisibles quelle que soit la
                  // longueur réelle de la barre. Échelle log toujours écartée (démarche
                  // complète dans docs/frontend/09-design-system.md, solution déjà validée à
                  // l'époque sur l'ancien Dashboard, réappliquée à l'identique ici le
                  // 2026-09-14 après un même symptôme constaté sur la version horizontale) :
                  // trompeuse pour un public non expert et incompatible avec les séries à
                  // valeurs `null` requises ci-dessous pour une couleur par barre. Solution :
                  // échelle linéaire + `minBarSize` (longueur plancher en pixels, jamais une
                  // barre invisible même pour une valeur minuscule) + légende explicative
                  // juste en dessous (Typography "Échelle linéaire...") -- jamais caché que
                  // les barres ne sont pas strictement proportionnelles pour les petites
                  // valeurs, juste rendu lisible.
                  // `d.label` reste la valeur BRUTE (clé de couleur/données) -- seul l'axe et
                  // l'étiquette de série affichent la traduction (2026-09-13, "la plateforme
                  // doit être entièrement en français").
                  yAxis={[{ scaleType: "band", data: criticalityData.map((d) => displayAxisLabel(d.label)) }]}
                  // Graduations de l'axe des valeurs (2026-09-14, demande de l'encadrant) --
                  // par défaut MUI X Charts pose une graduation tous les ~500 sur une plage
                  // 0-13 500 (27 graduations), surchargé visuellement. `tickNumber` : une
                  // SUGGESTION du nombre de graduations (d3-scale choisit ensuite les valeurs
                  // "rondes" les plus proches, jamais un nombre exact garanti) -- 5 ici donne
                  // 5-6 graduations lisibles. `valueFormatter` : format compact ("13,5k" au
                  // lieu de "13500"), uniquement au-delà de 1000 (les petites valeurs restent
                  // en clair, pas d'arrondi trompeur sur "298").
                  xAxis={[
                    {
                      tickNumber: 5,
                      valueFormatter: (value: number) =>
                        Math.abs(value) >= 1000
                          ? `${(value / 1000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })}k`
                          : String(value),
                    },
                  ]}
                  // Une série PAR criticité (pas une seule série multi-couleurs) : MUI X Charts
                  // n'applique une couleur par barre que via des séries séparées -- chaque
                  // série ne porte de valeur qu'à sa propre position, `null` ailleurs. Couleurs
                  // = mêmes tokens que les cartes de stats juste au-dessus et que la légende de
                  // criticité partout ailleurs dans l'app (theme/colors.ts).
                  series={criticalityData.map((d, i) => ({
                    label: displayAxisLabel(d.label),
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

      {/* Répartition par source (2026-09-12, demande de l'encadrant après démo) -- une carte
          par firewall (tuiles compactes + période couverte + dernier import), volontairement
          sans mini-graphiques par carte (confirmé par l'encadrant) : les Pie/Bar Chart
          ci-dessus restent uniquement globaux. */}
      <Typography variant="subtitle1" sx={{ mt: 4, mb: 2 }}>
        Répartition par source
      </Typography>
      {sourceOptions.length === 0 && (
        <Alert severity="info">Aucune source connue.</Alert>
      )}
      {sourceOptions.length > 0 && (
        <Grid container spacing={2}>
          {sourceOptions.map((source) => (
            <Grid key={source} size={{ xs: 12, md: 6, lg: 4 }}>
              <SourceDashboardCard source={source} />
            </Grid>
          ))}
        </Grid>
      )}

      {/* "État des sources" (2026-09-12, demande de l'encadrant) -- tableau compact, sous la
          répartition par source. Réutilise le calcul de diff DÉJÀ EXISTANT (Services/
          validation_cycle_engine.py::compute_diff, même résumé que Cycle de validation) --
          aucune nouvelle logique de calcul, voir SourceStatusRow.tsx pour la précédence
          Premier cycle / Conforme / N écart(s). */}
      {sourceOptions.length > 0 && (
        <>
          <Typography variant="subtitle1" sx={{ mt: 4, mb: 2 }}>
            État des sources
          </Typography>
          <Table size="small" sx={{ maxWidth: 900 }}>
            <TableHead>
              <TableRow>
                <TableCell>Source</TableCell>
                <TableCell>Dernier import</TableCell>
                <TableCell>Dernière validation</TableCell>
                <TableCell>État</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sourceOptions.map((source) => (
                <SourceStatusRow key={source} source={source} />
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </Box>
  );
}

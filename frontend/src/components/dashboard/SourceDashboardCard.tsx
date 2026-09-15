import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import { useFlows } from "../../hooks/useFlows";
import { useSourceCoverageFor } from "../../hooks/useSourceCoverage";
import { CRITICALITY_ORDER, STATUS_COLORS, criticalityColor, displayAxisLabel } from "../../theme/colors";

// Carte "Répartition par source" du Dashboard (2026-09-12, demande de l'encadrant après démo
// -- refonte : au lieu des chiffres agrégés de toutes les sources mélangées, une carte par
// firewall). Tuiles compactes + période + dernier import -- volontairement PAS de mini-
// graphiques par carte (confirmé par l'encadrant), les Pie/Bar Charts restent uniquement
// globaux dans la section "Vue d'ensemble" de DashboardPage.tsx. Réutilise useFlows({source,
// limit:1}).summary (même agrégat déjà servant FlowsTablePage/FlowDetailDrawer), aucune
// nouvelle logique d'agrégation -- seule nouveauté : useSourceCoverageFor pour la période.
export function SourceDashboardCard({ source }: { source: string }) {
  const { data, isLoading } = useFlows({ source, limit: 1 });
  const coverage = useSourceCoverageFor(source);

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
          {source}
        </Typography>

        {isLoading && <Skeleton variant="rounded" height={96} />}

        {data && (
          <>
            <Stack direction="row" spacing={2} sx={{ mb: 1.5, flexWrap: "wrap" }}>
              <Typography variant="body2">
                Total flux : <strong>{data.summary.total_flows}</strong>
              </Typography>
              <Typography variant="body2" sx={{ color: STATUS_COLORS.good }}>
                Autorisé : <strong>{data.summary.allow_count}</strong>
              </Typography>
              <Typography variant="body2" sx={{ color: STATUS_COLORS.critical }}>
                Bloqué : <strong>{data.summary.block_count}</strong>
              </Typography>
            </Stack>

            <Stack direction="row" spacing={0.5} sx={{ mb: 1.5, flexWrap: "wrap" }}>
              {CRITICALITY_ORDER.map((label) => {
                const count = data.summary.criticality_breakdown[label];
                if (!count) return null;
                return (
                  <Chip
                    key={label}
                    size="small"
                    label={`${displayAxisLabel(label)} : ${count}`}
                    sx={{ backgroundColor: criticalityColor(label), color: "#fff" }}
                  />
                );
              })}
            </Stack>
          </>
        )}

        {coverage && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Période : {coverage.first_seen_at ? new Date(coverage.first_seen_at).toLocaleString("fr-FR") : "—"}
            {" → "}
            {coverage.last_seen_at ? new Date(coverage.last_seen_at).toLocaleString("fr-FR") : "—"}
            {coverage.last_imported_at && (
              <>
                <br />
                Dernier import : {new Date(coverage.last_imported_at).toLocaleString("fr-FR")}
              </>
            )}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

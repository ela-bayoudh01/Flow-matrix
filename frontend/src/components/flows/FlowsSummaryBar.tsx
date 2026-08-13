import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { FlowsSummary } from "../../api/types";

function StatTile({ label, value }: { label: string; value: number | string }) {
  return (
    <Card variant="outlined" sx={{ minWidth: 140 }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h5">{value}</Typography>
      </CardContent>
    </Card>
  );
}

export function FlowsSummaryBar({ summary }: { summary: FlowsSummary }) {
  return (
    <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: "wrap" }}>
      <StatTile label="Total flux" value={summary.total_flows} />
      <StatTile label="Allow" value={summary.allow_count} />
      <StatTile label="Block" value={summary.block_count} />
      {Object.entries(summary.criticality_breakdown).map(([label, count]) => (
        <StatTile key={label} label={`Criticité : ${label}`} value={count} />
      ))}
    </Stack>
  );
}

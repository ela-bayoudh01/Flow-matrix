import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { FINDING_TYPE_LABELS, FINDING_TYPE_COLORS } from "../../theme/colors";

const LEGEND_ITEMS = Object.entries(FINDING_TYPE_LABELS).map(([type, label]) => ({
  type,
  label,
  color: FINDING_TYPE_COLORS[type],
}));

export function RecommendationsLegend() {
  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
        {LEGEND_ITEMS.map(({ type, label, color }) => (
          <Stack key={type} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <Box sx={{ width: 16, height: 16, borderRadius: 0.5, backgroundColor: color }} />
            <Typography variant="body2">{label}</Typography>
          </Stack>
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
        Diagnostic sur les règles ACL déjà appliquées par le firewall, à partir du trafic
        observé -- jamais une proposition de nouvelle règle (rôle futur de l'ACL Engine).
      </Typography>
    </Box>
  );
}

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { INTENT_LABELS, INTENT_COLORS } from "../../theme/colors";

const LEGEND_ITEMS = Object.entries(INTENT_LABELS).map(([intent, label]) => ({
  intent,
  label,
  color: INTENT_COLORS[intent],
}));

export function AclProposalsLegend() {
  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
        {LEGEND_ITEMS.map(({ intent, label, color }) => (
          <Stack key={intent} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <Box sx={{ width: 16, height: 16, borderRadius: 0.5, backgroundColor: color }} />
            <Typography variant="body2">{label}</Typography>
          </Stack>
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
        Propositions de règles ACL en moindre privilège -- jamais appliquées automatiquement au
        firewall, toujours à vérifier et intégrer manuellement dans FMC après validation.
      </Typography>
    </Box>
  );
}

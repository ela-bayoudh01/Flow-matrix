import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { CRITICALITY_ORDER, CRITICALITY_COLORS, STATUS_COLORS } from "../../theme/colors";

const NON_QUALIFIE_COLOR = STATUS_COLORS.muted;

const LEGEND_ITEMS = [...CRITICALITY_ORDER.map((label) => ({ label, color: CRITICALITY_COLORS[label] })), { label: "non qualifié", color: NON_QUALIFIE_COLOR }];

export function MatrixLegend() {
  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
        {LEGEND_ITEMS.map(({ label, color }) => (
          <Stack key={label} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <Box sx={{ width: 16, height: 16, borderRadius: 0.5, backgroundColor: color, border: "1px solid rgba(0,0,0,0.15)" }} />
            <Typography variant="body2">{label}</Typography>
          </Stack>
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
        La cellule prend la couleur de son flux le plus critique, même si celui-ci est minoritaire.
      </Typography>
    </Box>
  );
}

import { useState } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import Tooltip from "@mui/material/Tooltip";
import Snackbar from "@mui/material/Snackbar";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import CloseIcon from "@mui/icons-material/Close";
import type { RuleRecommendationOut } from "../../api/types";
import { useReviewRecommendation } from "../../hooks/useRecommendations";
import { FINDING_TYPE_LABELS, FINDING_TYPE_COLORS, validationStatusColor } from "../../theme/colors";

// "Traiter" n'a pas le même sens selon le type de finding : resserrer une règle trop
// permissive, supprimer une règle obsolète -- mais pour "sans_regle_explicite", il n'y a pas
// de règle à modifier (le firewall bloque déjà par défaut). Demande explicite de Loulou
// (2026-08-13) : ce sens différent doit être visible sans avoir à demander.
const SANS_REGLE_EXPLICITE_HELP =
  "Pour ce type de finding, « Traiter » signifie : pris connaissance, à formaliser dans une " +
  "future règle explicite -- pas un resserrement de règle existante (il n'y en a pas) ni une " +
  "action d'urgence si le trafic est actuellement bloqué par défaut.";

function EvidenceRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" spacing={1} sx={{ py: 0.25 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 220 }}>
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Stack>
  );
}

function formatEvidenceRows(recommendation: RuleRecommendationOut): { label: string; value: string }[] {
  const evidence = recommendation.evidence ?? {};
  const rows: { label: string; value: string }[] = [];

  switch (recommendation.finding_type) {
    case "trop_permissive":
      rows.push(
        { label: "Ports distincts", value: String(evidence.distinct_dst_port ?? "?") },
        { label: "IP destination distinctes", value: String(evidence.distinct_dst_ip ?? "?") },
        { label: "Paires de zones distinctes", value: String(evidence.distinct_zone_pairs ?? "?") },
        {
          label: "Ports sensibles observés",
          value: Array.isArray(evidence.sensitive_ports_observed) && evidence.sensitive_ports_observed.length > 0
            ? evidence.sensitive_ports_observed.join(", ")
            : "aucun",
        },
        { label: "Flux high/critical concernés", value: String(evidence.high_or_critical_flow_count ?? 0) },
      );
      break;
    case "obsolete":
      rows.push(
        { label: "Dernière observation de la règle", value: String(evidence.rule_last_seen_at ?? "?") },
        { label: "Référence (fin de la fenêtre de données)", value: String(evidence.dataset_reference_at ?? "?") },
        { label: "Jours d'inactivité", value: String(evidence.inactivity_days ?? "?") },
        { label: "Seuil configuré", value: `${evidence.threshold_days ?? "?"} jours` },
      );
      break;
    case "sans_regle_explicite":
      rows.push(
        { label: "Connexions autorisées (allow)", value: String(evidence.allow_count ?? 0) },
        { label: "Connexions bloquées (block)", value: String(evidence.block_count ?? 0) },
        { label: "Flux high/critical concernés", value: String(evidence.high_or_critical_flow_count ?? 0) },
      );
      break;
    default:
      break;
  }

  return rows;
}

interface RecommendationDetailDrawerProps {
  recommendation: RuleRecommendationOut | null;
  onClose: () => void;
}

export function RecommendationDetailDrawer({ recommendation, onClose }: RecommendationDetailDrawerProps) {
  const reviewRecommendation = useReviewRecommendation();
  const [feedback, setFeedback] = useState<string | null>(null);

  if (!recommendation) {
    return <Drawer anchor="right" open={false} onClose={onClose} />;
  }

  const isSansRegleExplicite = recommendation.finding_type === "sans_regle_explicite";
  const note = typeof recommendation.evidence?.note === "string" ? recommendation.evidence.note : null;

  return (
    <Drawer anchor="right" open={!!recommendation} onClose={onClose}>
      <Box sx={{ width: { xs: "100vw", md: 520 }, p: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
          <Stack spacing={1}>
            <Chip
              size="small"
              label={FINDING_TYPE_LABELS[recommendation.finding_type] ?? recommendation.finding_type}
              sx={{
                backgroundColor: FINDING_TYPE_COLORS[recommendation.finding_type] ?? "#9e9e9e",
                color: "#fff",
                width: "fit-content",
              }}
            />
            <Typography variant="h6">
              {isSansRegleExplicite
                ? `${recommendation.ingress_zone} → ${recommendation.egress_zone}`
                : recommendation.rule_name}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {recommendation.source} · {recommendation.flow_count} flux concerné(s)
            </Typography>
          </Stack>
          <IconButton onClick={onClose} aria-label="Fermer">
            <CloseIcon />
          </IconButton>
        </Box>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Preuve (evidence)
        </Typography>
        {formatEvidenceRows(recommendation).map((row) => (
          <EvidenceRow key={row.label} {...row} />
        ))}
        {note && (
          <Alert severity="info" sx={{ mt: 2 }}>
            {note}
          </Alert>
        )}

        <Box sx={{ mt: 3 }}>
          {recommendation.status === "pending" ? (
            <>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <Button
                  size="small"
                  color="success"
                  variant="outlined"
                  loading={reviewRecommendation.isPending}
                  onClick={() =>
                    reviewRecommendation.mutate(
                      { id: recommendation.id, payload: { status: "acknowledged" } },
                      { onSuccess: () => setFeedback("Finding traité") },
                    )
                  }
                >
                  Traiter
                </Button>
                <Button
                  size="small"
                  color="error"
                  variant="outlined"
                  loading={reviewRecommendation.isPending}
                  onClick={() =>
                    reviewRecommendation.mutate(
                      { id: recommendation.id, payload: { status: "dismissed" } },
                      { onSuccess: () => setFeedback("Finding rejeté") },
                    )
                  }
                >
                  Rejeter
                </Button>
                {isSansRegleExplicite && (
                  <Tooltip title={SANS_REGLE_EXPLICITE_HELP}>
                    <InfoOutlinedIcon fontSize="small" color="action" />
                  </Tooltip>
                )}
              </Stack>
              {isSansRegleExplicite && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                  {SANS_REGLE_EXPLICITE_HELP}
                </Typography>
              )}
            </>
          ) : (
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Chip
                size="small"
                variant="outlined"
                label={recommendation.status}
                sx={{ borderColor: validationStatusColor(recommendation.status), color: validationStatusColor(recommendation.status) }}
              />
              {recommendation.reviewed_at && (
                <Typography variant="body2" color="text.secondary">
                  le {recommendation.reviewed_at}
                </Typography>
              )}
            </Stack>
          )}
        </Box>
      </Box>

      <Snackbar open={!!feedback} autoHideDuration={2500} onClose={() => setFeedback(null)} message={feedback} />
    </Drawer>
  );
}

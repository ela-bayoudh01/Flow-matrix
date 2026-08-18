import { useState } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Snackbar from "@mui/material/Snackbar";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DownloadIcon from "@mui/icons-material/Download";
import type { AclProposalOut } from "../../api/types";
import { useAclProposalHistory, useReviewAclProposal } from "../../hooks/useAclProposals";
import { INTENT_LABELS, INTENT_COLORS, validationStatusColor } from "../../theme/colors";

function RationaleRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" spacing={1} sx={{ py: 0.25 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 200 }}>
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Stack>
  );
}

function formatRationaleRows(proposal: AclProposalOut): { label: string; value: string }[] {
  const r = proposal.rationale ?? {};
  const rows: { label: string; value: string }[] = [];

  if (proposal.intent === "create") {
    rows.push(
      { label: "Flux à l'origine", value: Array.isArray(r.flow_ids) ? `${r.flow_ids.length} flux validé(s)` : "?" },
      { label: "IP source distinctes", value: String(r.distinct_src_ip ?? "?") },
      { label: "IP destination distinctes", value: String(r.distinct_dst_ip ?? "?") },
    );
  } else if (proposal.intent === "tighten" || proposal.intent === "revoke") {
    const evidence = (r.evidence as Record<string, unknown>) ?? {};
    rows.push({ label: "Note du finding", value: typeof evidence.note === "string" ? evidence.note : "voir finding lié" });
  } else if (proposal.intent === "manual") {
    rows.push({ label: "Justification", value: typeof r.note === "string" ? r.note : "?" });
    if (r.created_by) rows.push({ label: "Ajouté par", value: String(r.created_by) });
  }

  if (proposal.source_recommendation_id) {
    rows.push({ label: "Finding lié", value: `Recommandation #${proposal.source_recommendation_id}` });
  }

  return rows;
}

interface AclProposalDetailDrawerProps {
  proposal: AclProposalOut | null;
  onClose: () => void;
}

export function AclProposalDetailDrawer({ proposal, onClose }: AclProposalDetailDrawerProps) {
  const reviewProposal = useReviewAclProposal();
  const { data: history } = useAclProposalHistory(proposal?.id ?? null);
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  if (!proposal) {
    return <Drawer anchor="right" open={false} onClose={onClose} />;
  }

  const ruleText = proposal.proposed_rule_text ?? "";
  const downloadName = `${proposal.suggested_rule_name ?? "proposition_acl"}.txt`;

  function handleCopy() {
    navigator.clipboard.writeText(ruleText).then(() => setCopied(true));
  }

  function handleDownload() {
    const blob = new Blob([ruleText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = downloadName;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Drawer anchor="right" open={!!proposal} onClose={onClose}>
      <Box sx={{ width: { xs: "100vw", md: 560 }, p: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
          <Stack spacing={1}>
            <Chip
              size="small"
              label={INTENT_LABELS[proposal.intent] ?? proposal.intent}
              sx={{ backgroundColor: INTENT_COLORS[proposal.intent] ?? "#9e9e9e", color: "#fff", width: "fit-content" }}
            />
            <Typography variant="h6">{proposal.suggested_rule_name}</Typography>
          </Stack>
          <IconButton onClick={onClose} aria-label="Fermer">
            <CloseIcon />
          </IconButton>
        </Box>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Fiche proposée
        </Typography>
        <Box
          component="pre"
          sx={{
            p: 1.5,
            backgroundColor: "action.hover",
            borderRadius: 1,
            fontSize: "0.8rem",
            whiteSpace: "pre-wrap",
            fontFamily: "monospace",
          }}
        >
          {ruleText}
        </Box>
        <Stack direction="row" spacing={1} sx={{ mt: 1, mb: 2 }}>
          <Button size="small" startIcon={<ContentCopyIcon />} onClick={handleCopy}>
            Copier la fiche
          </Button>
          <Button size="small" startIcon={<DownloadIcon />} onClick={handleDownload}>
            Télécharger (.txt)
          </Button>
        </Stack>

        <Divider sx={{ my: 2 }} />

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Preuve / justification
        </Typography>
        {formatRationaleRows(proposal).map((row) => (
          <RationaleRow key={row.label} {...row} />
        ))}

        <Divider sx={{ my: 2 }} />

        <Box sx={{ mb: 2 }}>
          {proposal.status === "pending" ? (
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                color="success"
                variant="outlined"
                loading={reviewProposal.isPending}
                onClick={() =>
                  reviewProposal.mutate(
                    { id: proposal.id, payload: { status: "approved" } },
                    { onSuccess: () => setFeedback("Proposition confirmée") },
                  )
                }
              >
                Confirmer
              </Button>
              <Button
                size="small"
                color="error"
                variant="outlined"
                loading={reviewProposal.isPending}
                onClick={() =>
                  reviewProposal.mutate(
                    { id: proposal.id, payload: { status: "rejected" } },
                    { onSuccess: () => setFeedback("Proposition rejetée") },
                  )
                }
              >
                Rejeter
              </Button>
            </Stack>
          ) : (
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Chip
                size="small"
                variant="outlined"
                label={proposal.status}
                sx={{ borderColor: validationStatusColor(proposal.status), color: validationStatusColor(proposal.status) }}
              />
              {proposal.validated_at && (
                <Typography variant="body2" color="text.secondary">
                  le {proposal.validated_at}
                </Typography>
              )}
            </Stack>
          )}
        </Box>

        <Divider sx={{ my: 2 }} />

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Historique
        </Typography>
        {history && history.items.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            Aucune revue encore enregistrée.
          </Typography>
        )}
        {history?.items.map((h) => (
          <Typography key={h.id} variant="body2" color="text.secondary">
            {h.created_at} -- {h.old_status ?? "—"} → {h.new_status} ({h.changed_by ?? "non renseigné"})
          </Typography>
        ))}
      </Box>

      <Snackbar
        open={copied}
        autoHideDuration={2000}
        onClose={() => setCopied(false)}
        message="Fiche copiée dans le presse-papier"
      />
      <Snackbar open={!!feedback} autoHideDuration={2500} onClose={() => setFeedback(null)} message={feedback} />
    </Drawer>
  );
}

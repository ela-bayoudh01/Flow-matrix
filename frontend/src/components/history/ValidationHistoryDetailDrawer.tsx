import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Divider from "@mui/material/Divider";
import Alert from "@mui/material/Alert";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import CloseIcon from "@mui/icons-material/Close";
import DownloadIcon from "@mui/icons-material/Download";
import type { FlowHistoryEntryOut } from "../../api/types";
import { api } from "../../api/client";
import { STATUS_LABELS, ACTION_LABELS } from "../../theme/colors";

// Panneau de détail pour une ligne de l'Historique (2026-09-05, bug réel signalé : les lignes
// n'étaient pas cliquables, aucun moyen de consulter/télécharger la fiche PDF d'un changement
// de règle depuis cette page). Même style que FlowDiffDetailDrawer/AclProposalDetailDrawer.
// FlowHistoryEntryOut uniquement (2026-09-13, fusion avec NetworkPolicy) -- une ligne
// "Sous-réseau" montre déjà tous ses champs directement dans le tableau de HistoryPage.tsx,
// pas besoin d'un panneau ; cliquer sur une telle ligne n'ouvre donc jamais ce composant.
interface ValidationHistoryDetailDrawerProps {
  entry: FlowHistoryEntryOut | null;
  onClose: () => void;
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <TableRow>
      <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>{label}</TableCell>
      <TableCell>{value}</TableCell>
    </TableRow>
  );
}

export function ValidationHistoryDetailDrawer({ entry, onClose }: ValidationHistoryDetailDrawerProps) {
  if (!entry) {
    return <Drawer anchor="right" open={false} onClose={onClose} />;
  }

  const isRuleChange = !!entry.justification;

  return (
    <Drawer anchor="right" open={!!entry} onClose={onClose}>
      <Box sx={{ width: { xs: "100vw", md: 480 }, p: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
          <Stack spacing={0.5}>
            <Typography variant="h6">
              {entry.src_ip} → {entry.dst_ip}
              {entry.dst_port !== null ? `:${entry.dst_port}` : ""}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {entry.source ?? "(source non renseignée)"} -- {entry.protocol}
            </Typography>
          </Stack>
          <IconButton onClick={onClose} aria-label="Fermer">
            <CloseIcon />
          </IconButton>
        </Box>

        <Table size="small">
          <TableBody>
            <DetailRow label="Date" value={new Date(entry.created_at).toLocaleString("fr-FR")} />
            <DetailRow
              label="Changement"
              value={`${entry.old_status ? (STATUS_LABELS[entry.old_status] ?? entry.old_status) : "—"} → ${STATUS_LABELS[entry.new_status] ?? entry.new_status}`}
            />
            <DetailRow label="Décidé par" value={entry.decided_by ?? "—"} />
          </TableBody>
        </Table>

        <Divider sx={{ my: 2 }} />

        {isRuleChange ? (
          <>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Changement de règle
            </Typography>
            <Table size="small" sx={{ mb: 2 }}>
              <TableBody>
                <DetailRow label="Action observée avant" value={entry.observed_action_before ? (ACTION_LABELS[entry.observed_action_before] ?? entry.observed_action_before) : "—"} />
                <DetailRow label="Action décidée" value={entry.decided_action ? (ACTION_LABELS[entry.decided_action] ?? entry.decided_action) : "—"} />
              </TableBody>
            </Table>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Justification
            </Typography>
            <Typography variant="body2" sx={{ mb: 2, whiteSpace: "pre-wrap" }}>
              {entry.justification}
            </Typography>
            <Button
              variant="contained"
              startIcon={<DownloadIcon />}
              component="a"
              href={api.actionChangeFicheUrl(entry.id)}
              download
            >
              Télécharger la fiche (PDF)
            </Button>
          </>
        ) : (
          <Alert severity="info">
            Validation classique (Valider/Bloquer immédiat) -- aucun changement de règle, aucune
            fiche associée. Pour changer explicitement l'action décidée d'un flux, utiliser le
            bouton "Changer la règle" depuis la page Cycle de validation -- seul espace de
            travail où une décision peut être prise sur un flux (2026-09-12, demande de
            l'encadrant).
          </Alert>
        )}
      </Box>
    </Drawer>
  );
}

import { useState, useEffect } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import { useFlowLogEntries } from "../../hooks/useFlowLogEntries";
import { TableSkeleton } from "../common/TableSkeleton";
import { formatBytes } from "./FlowsTable";
import { ACTION_COLORS } from "../../theme/colors";
import type { FlowOut } from "../../api/types";

const PAGE_SIZE = 50;

// Drill-down (2026-09-06, demande de l'encadrant) : occurrence_count agrège potentiellement
// des milliers de connexions individuelles -- jamais consultables une par une jusqu'ici.
// Ouvert en cliquant sur le compteur d'occurrences d'un Flow (Table des flux, Cycle de
// validation, panneau de détail) -- une connexion individuelle a toujours UNE action précise
// (jamais "Mixed", qui n'existe qu'au niveau agrégé du Flow), pas besoin de describeAction ici.
interface FlowLogEntriesDrawerProps {
  flow: FlowOut | null;
  onClose: () => void;
}

export function FlowLogEntriesDrawer({ flow, onClose }: FlowLogEntriesDrawerProps) {
  const [page, setPage] = useState(0);
  const { data, isLoading, isError, error } = useFlowLogEntries(
    flow?.id ?? null,
    { limit: PAGE_SIZE, offset: page * PAGE_SIZE },
  );

  // Repart de la première page à chaque nouveau Flow ouvert -- jamais rester bloqué sur une
  // page 3 d'un précédent flux plus volumineux.
  useEffect(() => setPage(0), [flow?.id]);

  function handleClose() {
    onClose();
  }

  return (
    <Dialog open={!!flow} onClose={handleClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        Connexions individuelles
        {flow && (
          <Typography variant="body2" color="text.secondary">
            {flow.src_ip} → {flow.dst_ip}
            {flow.dst_port !== null ? `:${flow.dst_port}` : ""} ({flow.protocol})
          </Typography>
        )}
      </DialogTitle>
      <DialogContent>
        {isLoading && <TableSkeleton rows={5} />}
        {isError && <Alert severity="error">{(error as Error).message}</Alert>}
        {data && data.items.length === 0 && (
          <Alert severity="info">Aucune connexion individuelle trouvée pour ce flux.</Alert>
        )}
        {data && data.items.length > 0 && (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {data.total_count} connexion(s) au total -- détail ligne par ligne, jamais un
              recalcul de l'agrégat affiché sur le Flow.
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Date</TableCell>
                  <TableCell>Action</TableCell>
                  <TableCell>Règle ACL</TableCell>
                  <TableCell>Port source</TableCell>
                  <TableCell>Envoyé</TableCell>
                  <TableCell>Reçu</TableCell>
                  <TableCell>Durée</TableCell>
                  <TableCell>Application</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{entry.first_packet_at ?? "—"}</TableCell>
                    <TableCell>
                      {entry.access_control_rule_action ? (
                        <Chip
                          size="small"
                          label={entry.access_control_rule_action}
                          sx={{ backgroundColor: ACTION_COLORS[entry.access_control_rule_action] ?? "#9e9e9e", color: "#fff" }}
                        />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>{entry.access_control_rule_name ?? "—"}</TableCell>
                    <TableCell>{entry.src_port ?? "—"}</TableCell>
                    <TableCell>{formatBytes(entry.initiator_bytes ?? 0)}</TableCell>
                    <TableCell>{formatBytes(entry.responder_bytes ?? 0)}</TableCell>
                    <TableCell>{entry.connection_duration ?? 0}s</TableCell>
                    <TableCell>{entry.web_application ?? entry.application_protocol ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Stack direction="row" spacing={2} sx={{ mt: 2, alignItems: "center", justifyContent: "flex-end" }}>
              <Typography variant="body2" color="text.secondary">
                {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.total_count)} sur {data.total_count}
              </Typography>
              <Button size="small" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                Précédent
              </Button>
              <Button size="small" disabled={(page + 1) * PAGE_SIZE >= data.total_count} onClick={() => setPage((p) => p + 1)}>
                Suivant
              </Button>
            </Stack>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Fermer</Button>
      </DialogActions>
    </Dialog>
  );
}

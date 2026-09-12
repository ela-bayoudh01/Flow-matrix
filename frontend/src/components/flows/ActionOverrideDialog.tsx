import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import DownloadIcon from "@mui/icons-material/Download";
import { useChangeFlowRule } from "../../hooks/useFlows";
import { api } from "../../api/client";
import type { FlowOut } from "../../api/types";
import { describeAction } from "../../theme/colors";

// Fenêtre du bouton dédié "Changer la règle" (2026-09-05, décision de conception après un
// test réel où la détection de contradiction sur Valider/Bloquer ne déclenchait la fenêtre
// dans aucun cas concret) -- SEULE ouverture possible de ce flux : résumé explicite +
// justification obligatoire + lien de téléchargement de la fiche PDF une fois enregistrée.
// Valider/Bloquer (FlowsTable.tsx, FlowDiffDetailDrawer.tsx) restent un clic simple et
// immédiat, n'ouvrent jamais cette fenêtre.
interface ActionOverrideDialogProps {
  flow: FlowOut | null;
  targetAction: "Allow" | "Block" | null;
  onClose: () => void;
}

export function ActionOverrideDialog({ flow, targetAction, onClose }: ActionOverrideDialogProps) {
  const changeRule = useChangeFlowRule();
  const [justification, setJustification] = useState("");
  const [historyId, setHistoryId] = useState<number | null>(null);

  const open = !!flow && !!targetAction;

  function handleClose() {
    setJustification("");
    setHistoryId(null);
    changeRule.reset();
    onClose();
  }

  async function handleConfirm() {
    if (!flow || !targetAction) return;
    await changeRule.mutateAsync({ flowId: flow.id, payload: { target_action: targetAction, justification } });
    // La mutation retourne le Flow, pas la ligne d'historique -- on va chercher l'entrée
    // qu'on vient de créer (la plus récente pour ce flow) pour construire le lien de la fiche.
    const history = await api.getValidationHistory({ flowId: flow.id, limit: 1 });
    setHistoryId(history.items[0]?.id ?? null);
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Changer la règle de ce flux</DialogTitle>
      <DialogContent>
        {flow && targetAction && !historyId && (
          <>
            <Typography variant="body2" sx={{ mb: 2 }}>
              Le flux de <strong>{flow.src_ip}</strong> vers <strong>{flow.dst_ip}</strong>, port{" "}
              <strong>{flow.dst_port ?? "any"}</strong>, application{" "}
              <strong>{flow.web_application ?? flow.application_protocol ?? "non renseignée"}</strong>, sera{" "}
              <strong>{targetAction === "Block" ? "Bloqué" : "Autorisé"}</strong>.
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              {/* Jamais le mot brut "Mixed" (2026-09-06) -- répartition chiffrée à la place. */}
              Action actuellement observée : {describeAction(flow.dominant_action, flow.allow_count, flow.block_count).label}.
            </Typography>
            <TextField
              label="Justification (obligatoire)"
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              multiline
              minRows={3}
              fullWidth
              required
              sx={{ mt: 1 }}
              helperText="Pourquoi ce changement ? Sera enregistré dans l'historique et inclus dans la fiche."
            />
            {changeRule.isError && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {(changeRule.error as Error).message}
              </Alert>
            )}
          </>
        )}

        {historyId && (
          <Alert severity="success">
            Décision enregistrée : flux {flow?.src_ip} → {flow?.dst_ip} maintenant décidé "{targetAction}".
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        {!historyId ? (
          <>
            <Button onClick={handleClose}>Annuler</Button>
            <Button
              variant="contained"
              color={targetAction === "Block" ? "error" : "success"}
              disabled={!justification.trim()}
              loading={changeRule.isPending}
              onClick={handleConfirm}
            >
              Confirmer le changement
            </Button>
          </>
        ) : (
          <>
            <Button
              startIcon={<DownloadIcon />}
              component="a"
              href={api.actionChangeFicheUrl(historyId)}
              download
            >
              Télécharger la fiche (PDF)
            </Button>
            <Button variant="contained" onClick={handleClose}>
              Fermer
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}

import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import DownloadIcon from "@mui/icons-material/Download";
import { useDeclareRuleEnforcementClaim, useRuleEnforcementClaim } from "../../hooks/useRuleEnforcementClaim";
import { api } from "../../api/client";
import type { FlowOut, RuleEnforcementClaimOut } from "../../api/types";

// "Déclarer la réclamation" (2026-09-10, demande de l'encadrant) -- SEUL déclencheur de cette
// fenêtre : uniquement sur un flux "regle_non_appliquee" (cf. FlowDiffDetailDrawer.tsx).
// Distinct d'ActionOverrideDialog : ne prend AUCUNE décision (jamais de justification ici),
// constate seulement qu'une décision déjà prise n'est toujours pas appliquée -- même schéma
// confirmer -> succès + téléchargement.
interface DeclareClaimDialogProps {
  flow: FlowOut | null;
  onClose: () => void;
}

export function DeclareClaimDialog({ flow, onClose }: DeclareClaimDialogProps) {
  const declareClaim = useDeclareRuleEnforcementClaim();
  const { data: existingClaim } = useRuleEnforcementClaim(flow?.id ?? null);
  const [claimResult, setClaimResult] = useState<RuleEnforcementClaimOut | null>(null);

  const open = !!flow;

  function handleClose() {
    setClaimResult(null);
    declareClaim.reset();
    onClose();
  }

  async function handleConfirm() {
    if (!flow) return;
    const result = await declareClaim.mutateAsync(flow.id);
    setClaimResult(result);
  }

  const nextClaimNumber = (existingClaim?.claim_count ?? 0) + 1;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Déclarer la réclamation</DialogTitle>
      <DialogContent>
        {flow && !claimResult && (
          <>
            <Typography variant="body2" sx={{ mb: 2 }}>
              Le flux de <strong>{flow.src_ip}</strong> vers <strong>{flow.dst_ip}</strong>, port{" "}
              <strong>{flow.dst_port ?? "any"}</strong> a une décision (<strong>{flow.decided_action}</strong>)
              toujours pas appliquée par le pare-feu.
            </Typography>
            {existingClaim && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                Écart détecté le {new Date(existingClaim.first_detected_at).toLocaleString("fr-FR")}
                {existingClaim.claim_count > 0 && existingClaim.last_claimed_at
                  ? ` : déjà réclamé ${existingClaim.claim_count} fois, dernière fois le ${new Date(existingClaim.last_claimed_at).toLocaleString("fr-FR")}`
                  : " : jamais encore réclamé"}
                . Ce sera la {nextClaimNumber}e réclamation.
              </Typography>
            )}
            {declareClaim.isError && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {(declareClaim.error as Error).message}
              </Alert>
            )}
          </>
        )}

        {claimResult && (
          <Alert severity="success">
            Réclamation enregistrée :{claimResult.claim_count}e réclamation pour ce flux.
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        {!claimResult ? (
          <>
            <Button onClick={handleClose}>Annuler</Button>
            <Button variant="contained" color="warning" loading={declareClaim.isPending} onClick={handleConfirm}>
              Confirmer la réclamation
            </Button>
          </>
        ) : (
          <>
            <Button
              startIcon={<DownloadIcon />}
              component="a"
              href={api.ruleEnforcementClaimFicheUrl(claimResult.id)}
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

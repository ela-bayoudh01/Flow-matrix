import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import { NetworkPolicyForm } from "./NetworkPolicyForm";

// Dialog autour de NetworkPolicyForm (2026-09-11, fusion "Politiques de sous-réseau" -> Cycle
// de validation) -- accès "Créer une politique" depuis ValidationCyclePage.tsx, soit par ligne
// de sous-réseau (CIDR pré-rempli), soit en accès général (CIDR vide, saisi librement). Même
// formulaire qu'auparavant sur /network-policies (NetworkPolicyForm, réutilisé tel quel), juste
// dans une boîte de dialogue plutôt qu'en ligne -- la page Cycle de validation n'a pas la place
// de l'afficher en permanence comme le faisait la page dédiée. Reste ouverte après succès (le
// bandeau de confirmation du formulaire doit rester visible) -- l'encadrant referme lui-même.
export interface NetworkPolicyFormDialogProps {
  open: boolean;
  onClose: () => void;
  source: string;
  srcCidr: string;
  onSrcCidrChange: (value: string) => void;
}

export function NetworkPolicyFormDialog({ open, onClose, source, srcCidr, onSrcCidrChange }: NetworkPolicyFormDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        Créer une politique de sous-réseau
        <IconButton size="small" onClick={onClose} aria-label="Fermer">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <NetworkPolicyForm source={source} srcCidr={srcCidr} onSrcCidrChange={onSrcCidrChange} />
      </DialogContent>
    </Dialog>
  );
}

import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import { useCreateManualAclProposal } from "../../hooks/useAclProposals";

const ACTION_OPTIONS = ["Allow", "Block", "Remove"];

interface ManualAclProposalFormProps {
  open: boolean;
  onClose: () => void;
}

// Découpe une zone de texte "une IP/CIDR par ligne" en liste -- pas de validation de format
// stricte ici (l'équipe réseau reste juge de ce qu'elle saisit), juste le nettoyage des lignes vides.
function parseNetworkLines(raw: string): string[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export function ManualAclProposalForm({ open, onClose }: ManualAclProposalFormProps) {
  const createManual = useCreateManualAclProposal();

  const [source, setSource] = useState("");
  const [ingressZone, setIngressZone] = useState("");
  const [egressZone, setEgressZone] = useState("");
  const [protocol, setProtocol] = useState("");
  const [dstPort, setDstPort] = useState("");
  const [srcNetworks, setSrcNetworks] = useState("");
  const [dstNetworks, setDstNetworks] = useState("");
  const [proposedAction, setProposedAction] = useState("Allow");
  const [suggestedRuleName, setSuggestedRuleName] = useState("");
  const [targetRuleName, setTargetRuleName] = useState("");
  const [justification, setJustification] = useState("");
  const [createdBy, setCreatedBy] = useState("");

  const canSubmit = justification.trim().length > 0;

  function reset() {
    setSource("");
    setIngressZone("");
    setEgressZone("");
    setProtocol("");
    setDstPort("");
    setSrcNetworks("");
    setDstNetworks("");
    setProposedAction("Allow");
    setSuggestedRuleName("");
    setTargetRuleName("");
    setJustification("");
    setCreatedBy("");
    createManual.reset();
  }

  function handleClose() {
    reset();
    onClose();
  }

  function handleSubmit() {
    createManual.mutate(
      {
        source: source || undefined,
        ingress_zone: ingressZone || undefined,
        egress_zone: egressZone || undefined,
        protocol: protocol || undefined,
        dst_port: dstPort ? Number(dstPort) : undefined,
        src_networks: parseNetworkLines(srcNetworks),
        dst_networks: parseNetworkLines(dstNetworks),
        proposed_action: proposedAction,
        suggested_rule_name: suggestedRuleName || undefined,
        target_rule_name: targetRuleName || undefined,
        justification,
        created_by: createdBy || undefined,
      },
      { onSuccess: handleClose },
    );
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Ajouter une proposition manuelle</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Pour un flux ou un équipement pas encore observé dans les logs -- la justification est
          obligatoire, c'est la seule preuve disponible pour une entrée manuelle.
        </Typography>

        {createManual.isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {(createManual.error as Error).message}
          </Alert>
        )}

        <Stack spacing={2}>
          <Stack direction="row" spacing={2}>
            <TextField label="Source (site)" size="small" fullWidth value={source} onChange={(e) => setSource(e.target.value)} />
          </Stack>
          <Stack direction="row" spacing={2}>
            <TextField label="Zone source" size="small" fullWidth value={ingressZone} onChange={(e) => setIngressZone(e.target.value)} />
            <TextField label="Zone destination" size="small" fullWidth value={egressZone} onChange={(e) => setEgressZone(e.target.value)} />
          </Stack>
          <Stack direction="row" spacing={2}>
            <TextField label="Protocole" size="small" fullWidth value={protocol} onChange={(e) => setProtocol(e.target.value)} />
            <TextField label="Port destination" size="small" type="number" fullWidth value={dstPort} onChange={(e) => setDstPort(e.target.value)} />
          </Stack>
          <TextField
            label="Réseaux source (une IP/CIDR par ligne)"
            size="small"
            multiline
            minRows={2}
            fullWidth
            value={srcNetworks}
            onChange={(e) => setSrcNetworks(e.target.value)}
          />
          <TextField
            label="Réseaux destination (une IP/CIDR par ligne)"
            size="small"
            multiline
            minRows={2}
            fullWidth
            value={dstNetworks}
            onChange={(e) => setDstNetworks(e.target.value)}
          />
          <TextField
            select
            label="Action proposée"
            size="small"
            fullWidth
            value={proposedAction}
            onChange={(e) => setProposedAction(e.target.value)}
          >
            {ACTION_OPTIONS.map((a) => (
              <MenuItem key={a} value={a}>
                {a}
              </MenuItem>
            ))}
          </TextField>
          <Stack direction="row" spacing={2}>
            <TextField
              label="Nom de règle suggéré (optionnel)"
              size="small"
              fullWidth
              value={suggestedRuleName}
              onChange={(e) => setSuggestedRuleName(e.target.value)}
            />
            <TextField
              label="Règle ciblée (optionnel)"
              size="small"
              fullWidth
              value={targetRuleName}
              onChange={(e) => setTargetRuleName(e.target.value)}
            />
          </Stack>
          <TextField
            label="Justification"
            required
            size="small"
            multiline
            minRows={2}
            fullWidth
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
          />
          <TextField label="Ajouté par" size="small" fullWidth value={createdBy} onChange={(e) => setCreatedBy(e.target.value)} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Annuler</Button>
        <Button variant="contained" disabled={!canSubmit} loading={createManual.isPending} onClick={handleSubmit}>
          Ajouter
        </Button>
      </DialogActions>
    </Dialog>
  );
}

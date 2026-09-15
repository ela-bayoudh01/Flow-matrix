import { useState } from "react";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import { useCreateNetworkPolicy } from "../../hooks/useNetworkPolicies";

// Formulaire "Créer une politique de sous-réseau" (2026-09-10, demande de l'encadrant) --
// extrait de NetworkPoliciesPage.tsx le 2026-09-11 pour être réutilisé TEL QUEL (même
// comportement, mêmes champs, même validation) par ValidationCyclePage.tsx (fusion des deux
// pages, demande de l'encadrant) : un seul formulaire, deux emplacements (en ligne sur
// NetworkPoliciesPage.tsx, dans une Dialog sur ValidationCyclePage.tsx via
// NetworkPolicyFormDialog.tsx) -- jamais deux implémentations susceptibles de diverger.
//
// `srcCidr`/`onSrcCidrChange` contrôlés par le parent (pas un state interne) : le CIDR peut
// être pré-rempli depuis l'extérieur (clic sur un sous-réseau suggéré/observé), tout en restant
// modifiable à la main ou saisi librement -- jamais validé comme un vrai CIDR (demande
// explicite de l'encadrant).
export interface NetworkPolicyFormProps {
  source: string;
  srcCidr: string;
  onSrcCidrChange: (value: string) => void;
}

export function NetworkPolicyForm({ source, srcCidr, onSrcCidrChange }: NetworkPolicyFormProps) {
  const createPolicy = useCreateNetworkPolicy();

  const [destination, setDestination] = useState("");
  const [protocol, setProtocol] = useState("");
  const [dstPort, setDstPort] = useState("");
  const [action, setAction] = useState<"Allow" | "Block">("Block");
  const [justification, setJustification] = useState("");
  const [decidedBy, setDecidedBy] = useState("");

  function handleSubmit() {
    createPolicy.mutate(
      {
        source: source || undefined,
        src_cidr: srcCidr.trim(),
        destination: destination.trim(),
        protocol: protocol.trim() || undefined,
        dst_port: dstPort ? Number(dstPort) : undefined,
        action,
        justification: justification.trim(),
        decided_by: decidedBy.trim() || undefined,
      },
      {
        // CIDR source volontairement PAS réinitialisé -- pratique pour enregistrer plusieurs
        // politiques successives sur le même sous-réseau (ex. deux ports différents).
        onSuccess: () => {
          setDestination("");
          setProtocol("");
          setDstPort("");
          setJustification("");
          setDecidedBy("");
        },
      },
    );
  }

  const canSubmit = !!srcCidr.trim() && !!destination.trim() && !!justification.trim();

  return (
    <Stack spacing={2}>
      <TextField
        label="CIDR source"
        value={srcCidr}
        onChange={(e) => onSrcCidrChange(e.target.value)}
        size="small"
        fullWidth
        required
        helperText='Pré-rempli en cliquant "Créer une politique" sur un sous-réseau, ou saisi librement -- jamais validé comme un vrai CIDR.'
      />
      <TextField
        label="Destination"
        value={destination}
        onChange={(e) => setDestination(e.target.value)}
        size="small"
        fullWidth
        required
        helperText="Zone, IP, ou CIDR -- texte libre."
      />
      <Stack direction="row" spacing={2}>
        <TextField
          label="Protocole (optionnel)"
          value={protocol}
          onChange={(e) => setProtocol(e.target.value)}
          size="small"
          sx={{ flex: 1 }}
        />
        <TextField
          label="Port (optionnel)"
          value={dstPort}
          onChange={(e) => setDstPort(e.target.value.replace(/\D/g, ""))}
          size="small"
          sx={{ flex: 1 }}
        />
      </Stack>
      <TextField select label="Action" value={action} onChange={(e) => setAction(e.target.value as "Allow" | "Block")} size="small">
        <MenuItem value="Allow">Autoriser</MenuItem>
        <MenuItem value="Block">Bloquer</MenuItem>
      </TextField>
      <TextField
        label="Justification"
        value={justification}
        onChange={(e) => setJustification(e.target.value)}
        multiline
        minRows={2}
        required
        helperText="Pourquoi cette politique ? Obligatoire."
      />
      <TextField label="Décidé par (optionnel)" value={decidedBy} onChange={(e) => setDecidedBy(e.target.value)} size="small" />

      {createPolicy.isError && <Alert severity="error">{(createPolicy.error as Error).message}</Alert>}
      {createPolicy.isSuccess && (
        <Alert severity="success" onClose={() => createPolicy.reset()}>
          Politique enregistrée.
        </Alert>
      )}

      <Button variant="contained" disabled={!canSubmit} loading={createPolicy.isPending} onClick={handleSubmit} sx={{ alignSelf: "flex-start" }}>
        Enregistrer la politique
      </Button>
    </Stack>
  );
}

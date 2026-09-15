import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import ToggleButton from "@mui/material/ToggleButton";
import DownloadIcon from "@mui/icons-material/Download";
import { useSourceOptions } from "../hooks/useSourceOptions";
import { useObservedSubnets, useNetworkPolicies } from "../hooks/useNetworkPolicies";
import { NetworkPolicyForm } from "../components/network-policies/NetworkPolicyForm";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { api } from "../api/client";
import { STATUS_COLORS, ACTION_LABELS } from "../theme/colors";
import { PREFIX_OPTIONS, DEFAULT_PREFIX_LENGTH } from "../constants/subnetPrefixes";

// Politiques de sous-réseau (2026-09-10, demande de l'encadrant) -- fonctionnalité NOUVELLE et
// VOLONTAIREMENT ISOLÉE : aucun lien avec Flow.decided_action, le diff de cycle, ou
// FlowSnapshot (cf. ValidationCyclePage.tsx, FlowDiffDetailDrawer.tsx). Trois sections
// indépendantes : sous-réseaux OBSERVÉS (suggestion, jamais une vérité), formulaire de
// création, et liste des politiques déjà enregistrées.
//
// Page retirée de la navigation le 2026-09-11 (fusion dans ValidationCyclePage.tsx, demande de
// l'encadrant après démo -- même principe que la mise en sourdine de Recommandations/
// Propositions ACL, cf. Sidebar.tsx) : code conservé tel quel, route directe (/network-policies)
// toujours fonctionnelle. Le formulaire de création (ci-dessous, NetworkPolicyForm) est
// désormais PARTAGÉ avec ValidationCyclePage.tsx -- un seul formulaire, deux emplacements.
export function NetworkPoliciesPage() {
  const sourceOptions = useSourceOptions();
  const [source, setSource] = useState("");
  const [prefixLength, setPrefixLength] = useState(DEFAULT_PREFIX_LENGTH);

  useEffect(() => {
    if (!source && sourceOptions.length > 0) setSource(sourceOptions[0]);
  }, [source, sourceOptions]);

  const { data: subnets, isLoading: subnetsLoading } = useObservedSubnets(source, prefixLength);
  const { data: policies, isLoading: policiesLoading } = useNetworkPolicies(source || undefined);

  const [srcCidr, setSrcCidr] = useState("");

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 1 }}>
        Politiques de sous-réseau
      </Typography>
     

      <TextField
        select
        size="small"
        label="Source (firewall)"
        value={source}
        onChange={(e) => setSource(e.target.value)}
        sx={{ minWidth: 220, mb: 3 }}
      >
        {sourceOptions.map((s) => (
          <MenuItem key={s} value={s}>
            {s}
          </MenuItem>
        ))}
      </TextField>

      {!source && sourceOptions.length === 0 && (
        <Alert severity="info">Aucune source connue: importe d'abord un log pour voir apparaître des sous-réseaux observés.</Alert>
      )}

      {source && (
        <Stack spacing={3}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>
                Sous-réseaux observés
              </Typography>
              

              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 2, flexWrap: "wrap" }}>
                <Typography variant="body2" color="text.secondary">
                  Granularité :
                </Typography>
                <ToggleButtonGroup
                  value={prefixLength}
                  exclusive
                  size="small"
                  onChange={(_, value: number | null) => value && setPrefixLength(value)}
                >
                  {PREFIX_OPTIONS.map((p) => (
                    <ToggleButton key={p} value={p}>
                      /{p}
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>
              </Stack>

              {subnetsLoading && <TableSkeleton rows={4} />}
              {subnets && subnets.items.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  Aucun flux pour cette source.
                </Typography>
              )}
              {subnets && subnets.items.length > 0 && (
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>CIDR suggéré</TableCell>
                      <TableCell>Machines distinctes</TableCell>
                      <TableCell>Flux associés</TableCell>
                      <TableCell />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {subnets.items.map((s) => (
                      <TableRow key={s.cidr}>
                        <TableCell>{s.cidr}</TableCell>
                        <TableCell>{s.machine_count}</TableCell>
                        <TableCell>{s.flow_count}</TableCell>
                        <TableCell>
                          <Button size="small" onClick={() => setSrcCidr(s.cidr)}>
                            Créer une politique
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card variant="outlined" sx={{ maxWidth: 640 }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 2 }}>
                Créer une politique de sous-réseau
              </Typography>
              <NetworkPolicyForm source={source} srcCidr={srcCidr} onSrcCidrChange={setSrcCidr} />
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>
                Politiques enregistrées
              </Typography>
              {policiesLoading && <TableSkeleton rows={4} />}
              {policies && policies.items.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  Aucune politique enregistrée pour l'instant.
                </Typography>
              )}
              {policies && policies.items.length > 0 && (
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>CIDR source</TableCell>
                      <TableCell>Destination</TableCell>
                      <TableCell>Port/Protocole</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell>Justification</TableCell>
                      <TableCell>Décidé par</TableCell>
                      <TableCell>Date</TableCell>
                      <TableCell />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {policies.items.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell>{p.src_cidr}</TableCell>
                        <TableCell>{p.destination}</TableCell>
                        <TableCell>
                          {p.dst_port ?? "tout port"} / {p.protocol ?? "tout protocole"}
                        </TableCell>
                        <TableCell sx={{ color: p.action === "Block" ? STATUS_COLORS.critical : STATUS_COLORS.good, fontWeight: 600 }}>
                          {ACTION_LABELS[p.action] ?? p.action}
                        </TableCell>
                        <TableCell sx={{ maxWidth: 220 }}>{p.justification}</TableCell>
                        <TableCell>{p.decided_by ?? "—"}</TableCell>
                        <TableCell>{new Date(p.created_at).toLocaleString("fr-FR")}</TableCell>
                        <TableCell>
                          <Button size="small" startIcon={<DownloadIcon />} component="a" href={api.networkPolicyFicheUrl(p.id)} download>
                            Fiche
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </Stack>
      )}
    </Box>
  );
}

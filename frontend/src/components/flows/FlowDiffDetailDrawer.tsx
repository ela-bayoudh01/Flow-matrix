import { useState, Fragment } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Snackbar from "@mui/material/Snackbar";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import CloseIcon from "@mui/icons-material/Close";
import type { FlowWithDiff } from "./FlowsTable";
import { useValidateFlow } from "../../hooks/useFlows";
import { ActionOverrideDialog } from "./ActionOverrideDialog";
import { DeclareClaimDialog } from "./DeclareClaimDialog";
import { FlowLogEntriesDrawer } from "./FlowLogEntriesDrawer";
import { invertedAction } from "../../api/types";
import { DIFF_STATUS_COLORS, DIFF_STATUS_LABELS, DIFF_FIELD_LABELS, STATUS_LABELS, ACTION_LABELS, describeAction, validationStatusColor, displayAxisLabel } from "../../theme/colors";

// Répartition chiffrée jamais le mot brut "Mixed" (2026-09-06) -- avant_allow/avant_block/
// apres_allow/apres_block ne sont renseignés par le backend que du côté effectivement
// "Mixed" (cf. Services/validation_cycle_engine.py::diff_for_flow). ACTION_LABELS[value] en
// plus (2026-09-12) : ce formateur sert aussi cycle_dominant_action (Allow/Block bruts pour
// un champ STRUCTURAL_FIELDS non-Mixed) -- jamais le mot anglais tel quel dans ce panneau.
function formatDiffAction(value: unknown, allowCount?: number, blockCount?: number): string {
  if (value === null || value === undefined) return "—";
  if (value === "Mixed" && allowCount !== undefined && blockCount !== undefined) {
    return describeAction("Mixed", allowCount, blockCount).label;
  }
  const text = String(value);
  return ACTION_LABELS[text] ?? text;
}

// Panneau de détail cliquable pour un écart de Cycle de validation -- remplace le tooltip
// discret d'origine (précision demandée par l'encadrant, 2026-08-21) : l'encadrant doit voir
// clairement OÙ se trouve la différence et CE QUI a changé (avant/après) avant de valider,
// pas juste un badge de couleur. Même style que AclProposalDetailDrawer (Drawer latéral).
interface FlowDiffDetailDrawerProps {
  flow: FlowWithDiff | null;
  onClose: () => void;
}

export function FlowDiffDetailDrawer({ flow, onClose }: FlowDiffDetailDrawerProps) {
  const validateFlow = useValidateFlow();
  const [feedback, setFeedback] = useState<string | null>(null);
  const [pendingRuleChange, setPendingRuleChange] = useState<"Allow" | "Block" | null>(null);
  const [showLogEntries, setShowLogEntries] = useState(false);
  const [showClaimDialog, setShowClaimDialog] = useState(false);

  // Valider/Bloquer : toujours immédiat, jamais de fenêtre -- même décision de conception
  // que FlowsTable.tsx (2026-09-05). "Changer la règle" est le seul bouton qui ouvre
  // ActionOverrideDialog, ci-dessous.
  function handleClick(status: "approved" | "blocked") {
    if (!flow) return;
    validateFlow.mutate(
      { flowId: flow.id, payload: { status } },
      { onSuccess: () => setFeedback(status === "approved" ? "Flux validé" : "Flux bloqué") },
    );
  }

  if (!flow) {
    return <Drawer anchor="right" open={false} onClose={onClose} />;
  }

  const status = flow.diff_status;
  const details = flow.diff_details;

  return (
    <Drawer anchor="right" open={!!flow} onClose={onClose}>
      <Box sx={{ width: { xs: "100vw", md: 520 }, p: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
          <Stack spacing={1}>
            {status && (
              <Chip
                size="small"
                label={DIFF_STATUS_LABELS[status]}
                sx={{ backgroundColor: DIFF_STATUS_COLORS[status], color: "#fff", width: "fit-content" }}
              />
            )}
            <Typography variant="h6">
              {flow.src_ip} → {flow.dst_ip}
              {flow.dst_port !== null ? `:${flow.dst_port}` : ""}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {flow.source ?? "(source non renseignée)"} : {flow.protocol}
            </Typography>
          </Stack>
          <IconButton onClick={onClose} aria-label="Fermer">
            <CloseIcon />
          </IconButton>
        </Box>

        {status === "nouveau" && (
          <Typography variant="body2" sx={{ mb: 2 }}>
            Ce flux n'existait pas dans la dernière Matrice Validée,première apparition
            depuis la baseline de cette source.
          </Typography>
        )}
        {status === "disparu" && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            
          </Typography>
        )}
        {status === "conforme" && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Identique à la dernière Matrice Validée ,rien à faire.
          </Typography>
        )}
        {status === "regle_non_appliquee" && (
          <>
            <Typography variant="body2" sx={{ mb: 1 }}>
               la règle demandée n'a pas encore été
              intégrée dans FMC.
            </Typography>
            {/* "Déclarer la réclamation" (2026-09-10) -- distinct de "Changer la règle" : ne
                prend aucune décision, constate juste qu'une décision déjà prise n'est
                toujours pas appliquée, avec une fiche + un suivi léger (première détection,
                dernière réclamation, nombre de fois réclamé). */}
            <Button size="small" color="error" variant="outlined" onClick={() => setShowClaimDialog(true)} sx={{ mb: 2 }}>
              Déclarer la réclamation
            </Button>
          </>
        )}

        {(status === "modifie" || status === "regle_non_appliquee") && details && Object.keys(details).length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Ce qui a changé depuis la dernière validation
            </Typography>
            <Table size="small">
              <TableBody>
                {Object.entries(details).map(([field, change]) => {
                  // "decided_action" (regle_non_appliquee) n'est PAS une transition avant->
                  // après de la même grandeur -- c'est une comparaison entre deux choses
                  // différentes (la décision prise vs l'action réellement observée). Une
                  // flèche "X → Y" laissait penser à un changement d'état, ambigu (signalé
                  // le 2026-09-06) -- deux lignes distinctes et étiquetées à la place.
                  if (field === "decided_action") {
                    return (
                      <Fragment key={field}>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>Décision (attendue)</TableCell>
                          <TableCell colSpan={3}>{formatDiffAction(change.avant, change.avant_allow, change.avant_block)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>Observé </TableCell>
                          <TableCell colSpan={3} sx={{ fontWeight: 600 }}>
                            {formatDiffAction(change.apres, change.apres_allow, change.apres_block)}
                          </TableCell>
                        </TableRow>
                      </Fragment>
                    );
                  }
                  return (
                    <TableRow key={field}>
                      <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>{DIFF_FIELD_LABELS[field] ?? field}</TableCell>
                      <TableCell>{formatDiffAction(change.avant, change.avant_allow, change.avant_block)}</TableCell>
                      <TableCell align="center">→</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>
                        {formatDiffAction(change.apres, change.apres_allow, change.apres_block)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </>
        )}

        <Divider sx={{ my: 2 }} />

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Détail du flux
        </Typography>
        <Table size="small">
          <TableBody>
            <TableRow>
              {/* Action de CE cycle (cycle_dominant_action), jamais lifetime -- ce panneau
                  n'existe que dans le contexte du Cycle de validation (2026-09-06). */}
              <TableCell sx={{ fontWeight: 600 }}>Action (ce cycle)</TableCell>
              <TableCell>{describeAction(flow.cycle_dominant_action, flow.cycle_allow_count, flow.cycle_block_count).label}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Zone source → destination</TableCell>
              <TableCell>
                {flow.ingress_zone ?? "(non renseigné)"} → {flow.egress_zone ?? "(non renseigné)"}
              </TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Règle ACL</TableCell>
              <TableCell>{flow.last_access_control_rule_name ?? "—"}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Criticité</TableCell>
              <TableCell>{flow.criticality_label ? displayAxisLabel(flow.criticality_label) : "non qualifié"}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Occurrences (ce cycle)</TableCell>
              {/* Drill-down (2026-09-06, demande de l'encadrant) : occurrence_count agrège
                  potentiellement des milliers de connexions, jamais consultables une par une
                  avant ce panneau -- volontairement une vue d'audit COMPLÈTE (jamais limitée
                  au cycle en cours), le même drill-down étant réutilisé partout où un Flow
                  s'affiche, y compris hors contexte de cycle. Le nombre "ce cycle" reste
                  affiché à gauche, mais le lien précise explicitement qu'il ouvre tout
                  l'historique -- ambiguïté signalée le 2026-09-06, jamais recoupée avant. */}
              <TableCell>
                {flow.cycle_occurrence_count}{" "}
                <Button size="small" onClick={() => setShowLogEntries(true)} sx={{ minWidth: 0, p: 0, textTransform: "none" }}>
                  voir tout l'historique ({flow.occurrence_count} connexion(s) au total)
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>

        <Divider sx={{ my: 2 }} />

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Validation
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          {flow.validation_status !== "pending" && (
            <Chip
              size="small"
              variant="outlined"
              label={STATUS_LABELS[flow.validation_status] ?? flow.validation_status}
              sx={{ borderColor: validationStatusColor(flow.validation_status), color: validationStatusColor(flow.validation_status) }}
            />
          )}
          {flow.validation_status === "pending" && (
            <>
              <Button size="small" color="success" variant="outlined" loading={validateFlow.isPending} onClick={() => handleClick("approved")}>
                Valider
              </Button>
              <Button size="small" color="error" variant="outlined" loading={validateFlow.isPending} onClick={() => handleClick("blocked")}>
                Bloquer
              </Button>
            </>
          )}
          {/* Bouton dédié "Changer la règle" -- toujours visible : SEUL déclencheur de la
              fenêtre de confirmation + justification + fiche PDF. */}
          <Button size="small" color="warning" variant="outlined" onClick={() => setPendingRuleChange(invertedAction(flow))}>
            Changer la règle
          </Button>
        </Stack>
      </Box>

      <ActionOverrideDialog flow={flow} targetAction={pendingRuleChange} onClose={() => setPendingRuleChange(null)} />
      <FlowLogEntriesDrawer flow={showLogEntries ? flow : null} onClose={() => setShowLogEntries(false)} />
      <DeclareClaimDialog flow={showClaimDialog ? flow : null} onClose={() => setShowClaimDialog(false)} />
      <Snackbar open={!!feedback} autoHideDuration={2500} onClose={() => setFeedback(null)} message={feedback} />
    </Drawer>
  );
}

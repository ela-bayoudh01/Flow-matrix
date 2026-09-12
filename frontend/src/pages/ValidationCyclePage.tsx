import { Fragment, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import ToggleButton from "@mui/material/ToggleButton";
import HistoryToggleOffOutlinedIcon from "@mui/icons-material/HistoryToggleOffOutlined";
import FiberNewOutlinedIcon from "@mui/icons-material/FiberNewOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import VisibilityOffOutlinedIcon from "@mui/icons-material/VisibilityOffOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import PriorityHighOutlinedIcon from "@mui/icons-material/PriorityHighOutlined";
import GppMaybeOutlinedIcon from "@mui/icons-material/GppMaybeOutlined";
import DownloadIcon from "@mui/icons-material/Download";
import { useValidationCycleDiff, useValidationCycleSubnetDiff, useCloseValidationCycle, useValidationCycles } from "../hooks/useValidationCycle";
import { useSourceOptions } from "../hooks/useSourceOptions";
import { useNetworkPolicies } from "../hooks/useNetworkPolicies";
import { useFlows, useQualifyFlows } from "../hooks/useFlows";
import { FlowsTable, type FlowWithDiff } from "../components/flows/FlowsTable";
import { FlowDiffDetailDrawer } from "../components/flows/FlowDiffDetailDrawer";
import { NetworkPolicyFormDialog } from "../components/network-policies/NetworkPolicyFormDialog";
import { FilterBar } from "../components/filters/FilterBar";
import { KeywordSearchField } from "../components/common/KeywordSearchField";
import { StatTile } from "../components/flows/FlowsSummaryBar";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { StatCardsSkeleton } from "../components/common/StatCardsSkeleton";
import { api } from "../api/client";
import { DIFF_STATUS_COLORS, DIFF_STATUS_LABELS, STATUS_COLORS } from "../theme/colors";
import { ecartsATraiter, type DiffStatus, type FlowFilterValues } from "../api/types";
import { PREFIX_OPTIONS, DEFAULT_PREFIX_LENGTH } from "../constants/subnetPrefixes";

// Ordre d'affichage des chips de filtre -- réutilisé aussi pour valider ?diff_status= depuis
// l'URL (tuile Dashboard "Règles non appliquées"), une seule liste, jamais deux définitions.
const DIFF_STATUS_VALUES: DiffStatus[] = ["nouveau", "modifie", "regle_non_appliquee", "disparu", "conforme"];

const DIFF_STATUS_ICONS: Record<DiffStatus, typeof FiberNewOutlinedIcon> = {
  nouveau: FiberNewOutlinedIcon,
  modifie: EditOutlinedIcon,
  regle_non_appliquee: GppMaybeOutlinedIcon,
  disparu: VisibilityOffOutlinedIcon,
  conforme: CheckCircleOutlineIcon,
};

// Ordre de priorité des chips d'écarts compactes par ligne de sous-réseau (ex. "2 Nouveau ·
// 1 Règle non appliquée") -- même priorité que les StatTiles ci-dessous (regle_non_appliquee
// avant nouveau, cf. commentaire plus bas). "disparu" informationnel, "conforme" (statut
// positif, pas un écart) en tout dernier -- TOUJOURS affiché si non nul (2026-09-12, demande
// de l'encadrant : sinon un sous-réseau avec des flux conformes ne le montre pas avant
// d'ouvrir la ligne, cassant la promesse "voir l'essentiel sans déplier"). La somme des
// badges affichés correspond ainsi toujours exactement au total de flux de la ligne.
const SUBNET_CHIP_ORDER: DiffStatus[] = ["regle_non_appliquee", "nouveau", "modifie", "disparu", "conforme"];

function subnetDiffChips(summary: Record<DiffStatus, number>): { status: DiffStatus; count: number }[] {
  return SUBNET_CHIP_ORDER.filter((status) => summary[status] > 0).map((status) => ({ status, count: summary[status] }));
}

// Restructuration "sous-réseau" (2026-09-11, demande directe de l'encadrant après
// démonstration) : le tableau principal de cette page regroupe désormais les Flow par CIDR
// suggéré (même mécanisme que /network-policies, désormais retirée de la navigation --
// Sidebar.tsx -- et fusionnée ici) plutôt que de lister chaque flux à plat. Le "+" par ligne
// déplie EXACTEMENT le même tableau de flux qu'avant (FlowsTable/FlowDiffDetailDrawer/
// Valider/Bloquer/Changer la règle inchangés), juste filtré par src_cidr -- aucune régression
// sur ce comportement déjà en place et déjà testé. Voir docs/13-cycle-de-validation.md.
export function ValidationCyclePage() {
  const sourceOptions = useSourceOptions();
  const [source, setSource] = useState<string>("");
  const [filters, setFilters] = useState<FlowFilterValues>({});
  // Point d'entrée depuis la tuile Dashboard "Règles non appliquées" (2026-09-10) --
  // ?diff_status=regle_non_appliquee présélectionne le filtre au chargement, la source reste
  // celle par défaut (un cycle est toujours propre à une source, cf. plus haut).
  const [searchParams] = useSearchParams();
  const [diffStatus, setDiffStatus] = useState<DiffStatus | undefined>(() => {
    const fromUrl = searchParams.get("diff_status");
    return DIFF_STATUS_VALUES.includes(fromUrl as DiffStatus) ? (fromUrl as DiffStatus) : undefined;
  });
  const [selectedFlow, setSelectedFlow] = useState<FlowWithDiff | null>(null);
  const [q, setQ] = useState("");
  const [showCycleHistory, setShowCycleHistory] = useState(false);
  const [showPolicyHistory, setShowPolicyHistory] = useState(false);

  // Tableau des sous-réseaux (2026-09-11) -- granularité + accordéon (un seul sous-réseau
  // déplié à la fois, décision actée après proposition : plus simple, cohérent avec le reste
  // du projet -- un flux/une cellule sélectionnés à la fois, jamais plusieurs volets ouverts
  // en parallèle avec chacun son propre FilterBar).
  const [prefixLength, setPrefixLength] = useState(DEFAULT_PREFIX_LENGTH);
  const [expandedCidr, setExpandedCidr] = useState<string | null>(null);

  // Formulaire "Créer une politique de sous-réseau" (2026-09-11) -- même NetworkPolicyForm que
  // /network-policies, dans une Dialog : ouverte depuis une ligne de sous-réseau (CIDR
  // pré-rempli) ou depuis l'accès général de l'en-tête (CIDR vide, saisi librement).
  const [policyDialogOpen, setPolicyDialogOpen] = useState(false);
  const [policyDialogCidr, setPolicyDialogCidr] = useState("");

  function openPolicyDialog(cidr: string) {
    setPolicyDialogCidr(cidr);
    setPolicyDialogOpen(true);
  }

  // Sélectionne automatiquement la première source connue tant que l'utilisateur n'a rien
  // choisi -- un cycle est toujours propre à une source, jamais un choix "toutes" possible.
  useEffect(() => {
    if (!source && sourceOptions.length > 0) setSource(sourceOptions[0]);
  }, [source, sourceOptions]);

  // Réinitialise le sous-réseau déplié quand la source ou la granularité change -- la ligne
  // affichée pourrait ne plus exister dans le nouveau regroupement.
  useEffect(() => {
    setExpandedCidr(null);
  }, [source, prefixLength]);

  // Diff GLOBAL de la source (StatTiles, bandeaux, texte de baseline) -- INDÉPENDANT du
  // sous-réseau déplié et des filtres/recherche ci-dessous (qui ne s'appliquent qu'au
  // sous-réseau ouvert) : ces totaux doivent rester vrais même quand rien n'est déplié.
  // limit: 1 -- seul `summary`/`cycles` importe ici, jamais `items` (même trick déjà utilisé
  // pour le bandeau "flux non qualifiés" ci-dessous).
  const { data, isLoading, isError, error } = useValidationCycleDiff({ source: source || undefined, limit: 1 });

  // Tableau principal : rollup du diff par sous-réseau CIDR observé.
  const { data: subnetDiff, isLoading: subnetDiffLoading } = useValidationCycleSubnetDiff(source, prefixLength);

  // Détail du sous-réseau déplié -- réutilise EXACTEMENT le même hook/endpoint que la Table
  // des flux/l'ancien tableau à plat, juste filtré par src_cidr en plus des filtres existants
  // (FilterBar/chips Écart/recherche, désormais contextuels au sous-réseau ouvert).
  const expandedQueryFilters = { ...filters, source: source || undefined, src_cidr: expandedCidr ?? undefined, diff_status: diffStatus, q, limit: 500 };
  const { data: expandedData, isLoading: expandedLoading } = useValidationCycleDiff(expandedQueryFilters, { enabled: !!expandedCidr });

  const closeCycle = useCloseValidationCycle();
  // Bandeau "flux non qualifiés" (2026-09-09, demande de l'encadrant) : couvre le cas où
  // l'étape Qualification a été zappée sur la page Import -- détection automatique plutôt que
  // de dépendre d'un bouton perdu ailleurs. limit=1 : seul summary.criticality_breakdown
  // importe ici, jamais les lignes elles-mêmes.
  const { data: flowsSummary } = useFlows({ source: source || undefined, limit: 1 }, { enabled: !!source });
  const qualifyFlows = useQualifyFlows(source || undefined);
  const unqualifiedCount = flowsSummary?.summary.criticality_breakdown.non_qualifie ?? 0;
  // "Cycles précédents" (2026-09-10, demande de l'encadrant) -- rapport de clôture
  // retéléchargeable depuis l'historique des cycles, pas seulement juste après la clôture.
  const { data: pastCycles } = useValidationCycles(source || undefined, 20);
  // "Politiques enregistrées" (2026-09-11, fusion de /network-policies) -- même liste/fiche
  // PDF qu'auparavant sur la page dédiée, repliable comme "Cycles précédents" ci-dessus.
  const { data: policies } = useNetworkPolicies(source || undefined);

  const cycle = source ? data?.cycles[source] : undefined;
  const expandedFlows: FlowWithDiff[] =
    expandedData?.items.map((item) => ({ ...item.flow, diff_status: item.diff_status, diff_details: item.diff_details })) ?? [];

  function handleClose() {
    closeCycle.mutate({ source });
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: "center", mb: 1, flexWrap: "wrap" }}>
        <Typography variant="h5">Cycle de validation</Typography>
        <TextField
          select
          size="small"
          label="Source (firewall)"
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            closeCycle.reset();
            qualifyFlows.reset();
          }}
          sx={{ minWidth: 220 }}
        >
          {sourceOptions.map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" size="small" disabled={!source} loading={closeCycle.isPending} onClick={handleClose}>
          Clôturer le cycle
        </Button>
        {/* Accès général "Créer une politique" (2026-09-11) -- en plus de l'accès par ligne de
            sous-réseau ci-dessous, CIDR laissé vide/saisi librement. */}
        <Button variant="outlined" size="small" disabled={!source} onClick={() => openPolicyDialog("")}>
          Créer une politique de sous-réseau
        </Button>
        <KeywordSearchField value={q} onChange={setQ} />
      </Stack>

      {!source && sourceOptions.length === 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Aucune source connue ,importe d'abord un log pour voir apparaître un cycle de validation.
        </Alert>
      )}

      {source && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {cycle
            ? `Dernière baseline (Matrice Validée) de ${source} : ${new Date(cycle.closed_at).toLocaleString("fr-FR")}${cycle.closed_by ? ` par ${cycle.closed_by}` : ""} (${cycle.flow_count} flux figés.)`
            : `Aucune baseline pour l'instant sur ${source} tous ses flux sont affichés comme "nouveau" (premier cycle).`}
        </Typography>
      )}

      {source && pastCycles && pastCycles.items.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Button size="small" onClick={() => setShowCycleHistory((v) => !v)} sx={{ mb: showCycleHistory ? 1 : 0 }}>
            {showCycleHistory ? "Masquer" : "Voir"} les cycles précédents ({pastCycles.items.length})
          </Button>
          {showCycleHistory && (
            <Table size="small" sx={{ maxWidth: 640 }}>
              <TableBody>
                {pastCycles.items.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>{new Date(c.closed_at).toLocaleString("fr-FR")}</TableCell>
                    <TableCell>{c.closed_by ?? "—"}</TableCell>
                    <TableCell>{c.flow_count} flux</TableCell>
                    <TableCell>
                      <Button size="small" startIcon={<DownloadIcon />} component="a" href={api.cycleReportUrl(c.id)} download>
                        Rapport
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Box>
      )}

      {closeCycle.isSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => closeCycle.reset()}>
          Cycle clôturé pour {closeCycle.data.source}
        </Alert>
      )}
      {closeCycle.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(closeCycle.error as Error).message}
        </Alert>
      )}

      {/* "Générer les propositions ACL pour ce cycle" retiré (2026-09-10, demande de
          l'encadrant) -- le module Propositions ACL reste mis en sourdine (cf. Sidebar.tsx,
          2026-09-04), ce bouton était resté un point d'entrée UI oublié malgré ça. Le Rapport
          de clôture + Déclarer la réclamation couvrent déjà l'essentiel de ce qu'il apportait.
          NE SUPPRIME AUCUN CODE/endpoint/modèle/test lié à l'ACL Engine -- uniquement ce
          point d'entrée, pour pouvoir le réactiver facilement plus tard si besoin (le bouton
          "Relance manuelle" de la page Propositions ACL, toujours mise en sourdine, reste
          intact derrière la route directe). */}
      {closeCycle.isSuccess && (
        <Stack direction="row" spacing={2} sx={{ mb: 2, alignItems: "center" }}>
          {/* Rapport de clôture (2026-09-10, demande de l'encadrant) -- récapitule toutes les
              décisions "Changer la règle" prises durant ce cycle en un seul PDF. Toujours
              régénéré à la demande, retéléchargeable plus tard via "Cycles précédents". */}
          <Button
            size="small"
            startIcon={<DownloadIcon />}
            component="a"
            href={api.cycleReportUrl(closeCycle.data.id)}
            download
          >
            Télécharger le rapport du cycle (PDF)
          </Button>
        </Stack>
      )}

      {data && data.summary.pending_review_count > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {data.summary.pending_review_count} écart(s) encore en attente de revue.
        </Alert>
      )}

      {/* Auto-détecté (2026-09-09, demande de l'encadrant) : couvre le cas où l'étape
          Qualification a été zappée sur la page Import -- criticality_label fait partie de
          STRUCTURAL_FIELDS (Services/validation_cycle_engine.py), un flux non qualifié fausse
          donc le diff autant qu'un flux non revu. */}
      {unqualifiedCount > 0 && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" loading={qualifyFlows.isPending} onClick={() => qualifyFlows.mutate()}>
              Lancer la qualification
            </Button>
          }
        >
          {unqualifiedCount} flux n'ont pas encore été qualifiés -- lancer la qualification pour
          une criticité à jour.
        </Alert>
      )}
      {qualifyFlows.isSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => qualifyFlows.reset()}>
          {qualifyFlows.data.total_qualified} flux qualifié(s) pour {source}.
        </Alert>
      )}
      {qualifyFlows.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(qualifyFlows.error as Error).message}
        </Alert>
      )}

      {isLoading && (
        <Box sx={{ mb: 2 }}>
          <StatCardsSkeleton />
        </Box>
      )}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data && (
        <>
          <Stack direction="row" spacing={2} sx={{ mb: 1, flexWrap: "wrap", alignItems: "stretch" }}>
            <StatTile
              label="Écarts à traiter"
              value={ecartsATraiter(data.summary)}
              icon={PriorityHighOutlinedIcon}
              color={ecartsATraiter(data.summary) > 0 ? STATUS_COLORS.serious : STATUS_COLORS.good}
            />
            {/* "Règle non appliquée" en premier des 3 -- affichage distinct et prioritaire
                demandé par l'encadrant (2026-09-03) : une décision humaine déjà prise, encore
                pas honorée par le pare-feu, mérite plus d'attention qu'une simple dérive. */}
            <StatTile
              label={DIFF_STATUS_LABELS.regle_non_appliquee}
              value={data.summary.regle_non_appliquee}
              icon={DIFF_STATUS_ICONS.regle_non_appliquee}
              color={DIFF_STATUS_COLORS.regle_non_appliquee}
            />
            <StatTile label={DIFF_STATUS_LABELS.nouveau} value={data.summary.nouveau} icon={DIFF_STATUS_ICONS.nouveau} color={DIFF_STATUS_COLORS.nouveau} />
            <StatTile label={DIFF_STATUS_LABELS.modifie} value={data.summary.modifie} icon={DIFF_STATUS_ICONS.modifie} color={DIFF_STATUS_COLORS.modifie} />
            <StatTile label={DIFF_STATUS_LABELS.conforme} value={data.summary.conforme} icon={DIFF_STATUS_ICONS.conforme} color={DIFF_STATUS_COLORS.conforme} />
          </Stack>
          {/* "Disparu" séparé du bloc "écarts" ci-dessus : informationnel uniquement, jamais
              une action à traiter -- décision actée le 2026-08-21 (le workflow de l'encadrant
              ne décrit que conforme/nouveau, jamais un 3e cas). */}
          <Stack direction="row" spacing={1} sx={{ mb: 2, alignItems: "center" }}>
            <StatTile label={`${DIFF_STATUS_LABELS.disparu} (informationnel)`} value={data.summary.disparu} icon={DIFF_STATUS_ICONS.disparu} color={DIFF_STATUS_COLORS.disparu} />
          </Stack>

          {/* Tableau des sous-réseaux (2026-09-11, restructuration demandée par l'encadrant) --
              même mécanisme de regroupement CIDR que l'ancienne page /network-policies. */}
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1, flexWrap: "wrap" }}>
            <Typography variant="subtitle1">Sous-réseaux observés</Typography>
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
          

          {subnetDiffLoading && <TableSkeleton rows={4} />}
          {subnetDiff && subnetDiff.items.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Aucun flux pour cette source.
            </Typography>
          )}
          {subnetDiff && subnetDiff.items.length > 0 && (
            <Table size="small" sx={{ mb: 3 }}>
              <TableHead>
                <TableRow>
                  <TableCell />
                  <TableCell>CIDR suggéré</TableCell>
                  <TableCell>Machines</TableCell>
                  <TableCell>Flux</TableCell>
                  <TableCell>Écarts de ce cycle</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {subnetDiff.items.map((item) => {
                  const isExpanded = expandedCidr === item.cidr;
                  return (
                    <Fragment key={item.cidr}>
                      <TableRow hover>
                        <TableCell sx={{ width: 40 }}>
                          {/* Bouton carré "+"/"−" plutôt qu'un chevron (demande de l'encadrant,
                              2026-09-11) -- même accordéon (un seul volet ouvert à la fois),
                              juste l'icône qui change de forme selon l'état. */}
                          <IconButton
                            size="small"
                            onClick={() => setExpandedCidr(isExpanded ? null : item.cidr)}
                            aria-label={isExpanded ? "Replier" : "Déplier"}
                            sx={{
                              width: 28,
                              height: 28,
                              borderRadius: 1,
                              border: "1px solid",
                              borderColor: "divider",
                              fontSize: 16,
                              fontWeight: 700,
                              lineHeight: 1,
                            }}
                          >
                            {isExpanded ? "−" : "+"}
                          </IconButton>
                        </TableCell>
                        <TableCell>{item.cidr}</TableCell>
                        <TableCell>{item.machine_count}</TableCell>
                        <TableCell>{item.flow_count}</TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.5 }}>
                            {subnetDiffChips(item.diff_summary).map(({ status, count }) => (
                              <Chip
                                key={status}
                                size="small"
                                label={`${count} ${DIFF_STATUS_LABELS[status]}`}
                                // "conforme" en contour discret (statut positif, pas un écart à
                                // traiter) -- même traitement déjà utilisé pour les chips de
                                // filtre "Écart" non actifs plus bas sur cette page, plutôt
                                // qu'un fond plein qui le confondrait visuellement avec les
                                // badges qui demandent vraiment une revue.
                                variant={status === "conforme" ? "outlined" : "filled"}
                                sx={
                                  status === "conforme"
                                    ? { borderColor: DIFF_STATUS_COLORS[status], color: DIFF_STATUS_COLORS[status] }
                                    : { backgroundColor: DIFF_STATUS_COLORS[status], color: "#fff" }
                                }
                              />
                            ))}
                          </Stack>
                        </TableCell>
                        <TableCell>
                          <Button size="small" onClick={() => openPolicyDialog(item.cidr)}>
                            Créer une politique
                          </Button>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell colSpan={6} sx={{ py: 0, borderBottom: isExpanded ? undefined : "none" }}>
                          <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                            <Box sx={{ py: 2 }}>
                              <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: "center", flexWrap: "wrap" }}>
                                <HistoryToggleOffOutlinedIcon fontSize="small" color="action" />
                                <Typography variant="body2" color="text.secondary">
                                  Écart :
                                </Typography>
                                <Chip
                                  size="small"
                                  label="Tout"
                                  variant={diffStatus === undefined ? "filled" : "outlined"}
                                  color={diffStatus === undefined ? "primary" : "default"}
                                  onClick={() => setDiffStatus(undefined)}
                                />
                                {DIFF_STATUS_VALUES.map((status) => (
                                  <Chip
                                    key={status}
                                    size="small"
                                    label={DIFF_STATUS_LABELS[status]}
                                    variant={diffStatus === status ? "filled" : "outlined"}
                                    onClick={() => setDiffStatus(status)}
                                    sx={
                                      diffStatus === status
                                        ? { backgroundColor: DIFF_STATUS_COLORS[status], color: "#fff" }
                                        : { borderColor: DIFF_STATUS_COLORS[status], color: DIFF_STATUS_COLORS[status] }
                                    }
                                  />
                                ))}
                              </Stack>
                              <FilterBar value={filters} onChange={setFilters} hideSourceFilter />
                              {expandedLoading && <TableSkeleton />}
                              {expandedData && (
                                <>
                                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                                    {expandedData.items.length} affichés sur {expandedData.total_count} au total dans {item.cidr}
                                  </Typography>
                                  <FlowsTable flows={expandedFlows} showDiffColumn onDiffClick={setSelectedFlow} />
                                </>
                              )}
                            </Box>
                          </Collapse>
                        </TableCell>
                      </TableRow>
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </>
      )}

      {/* "Politiques enregistrées" (2026-09-11, fusion de /network-policies) -- même liste/fiche
          PDF qu'auparavant sur la page dédiée, repliable comme "Cycles précédents" ci-dessus. */}
      {source && policies && policies.items.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Button size="small" onClick={() => setShowPolicyHistory((v) => !v)} sx={{ mb: showPolicyHistory ? 1 : 0 }}>
            {showPolicyHistory ? "Masquer" : "Voir"} les politiques de sous-réseau enregistrées ({policies.items.length})
          </Button>
          {showPolicyHistory && (
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
                      {p.dst_port ?? "any"} / {p.protocol ?? "any"}
                    </TableCell>
                    <TableCell sx={{ color: p.action === "Block" ? STATUS_COLORS.critical : STATUS_COLORS.good, fontWeight: 600 }}>
                      {p.action}
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
        </Box>
      )}

      <FlowDiffDetailDrawer flow={selectedFlow} onClose={() => setSelectedFlow(null)} />
      <NetworkPolicyFormDialog
        open={policyDialogOpen}
        onClose={() => setPolicyDialogOpen(false)}
        source={source}
        srcCidr={policyDialogCidr}
        onSrcCidrChange={setPolicyDialogCidr}
      />
    </Box>
  );
}

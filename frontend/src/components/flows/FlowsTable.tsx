import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type CellClickedEvent, type ColDef } from "ag-grid-community";
import { useMemo, useState } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import type { DiffFieldChange, DiffStatus, FlowOut } from "../../api/types";
import { invertedAction } from "../../api/types";
import { useValidateFlow } from "../../hooks/useFlows";
import { ActionOverrideDialog } from "./ActionOverrideDialog";
import { FlowLogEntriesDrawer } from "./FlowLogEntriesDrawer";
import { criticalityColor, validationStatusColor, describeAction, displayAxisLabel, DIFF_STATUS_COLORS, DIFF_STATUS_LABELS, STATUS_LABELS } from "../../theme/colors";
import { appGridTheme } from "../../theme/agGridTheme";
import { SimpleColumnFilter } from "../common/SimpleColumnFilter";

ModuleRegistry.registerModules([AllCommunityModule]);

// Un Flow décoré de son écart par rapport à la dernière Matrice Validée (Cycle de
// validation) -- champs optionnels : FlowsTable reste utilisable sans ça (Table des flux,
// panneau de détail de la Matrice), la colonne "Écart" n'apparaît que si showDiffColumn est
// vrai ET que le flow correspondant porte ces champs (page Cycle de validation).
export interface FlowWithDiff extends FlowOut {
  diff_status?: DiffStatus;
  diff_details?: Record<string, DiffFieldChange> | null;
}

// Cliquable plutôt qu'un survol (précision demandée par l'encadrant, 2026-08-21) : ce qui a
// changé doit être visible d'un clic dans un panneau, jamais caché derrière un tooltip
// discret -- cf. FlowDiffDetailDrawer.tsx, ouvert par onDiffClick.
function DiffChip({ flow, onClick }: { flow: FlowWithDiff; onClick?: (flow: FlowWithDiff) => void }) {
  if (!flow.diff_status) return null;
  return (
    <Chip
      size="small"
      label={DIFF_STATUS_LABELS[flow.diff_status]}
      onClick={onClick ? () => onClick(flow) : undefined}
      sx={{ backgroundColor: DIFF_STATUS_COLORS[flow.diff_status], color: "#fff", cursor: onClick ? "pointer" : "default" }}
    />
  );
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  const units = ["Ko", "Mo", "Go", "To"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

// Indicateur, pas un mode de coloration ni une nouvelle détection : une forte asymétrie sur
// un port/une zone inhabituels peut être un signal d'exfiltration ou de téléchargement massif
// -- laissé à l'appréciation de l'analyste, jamais auto-signalé comme suspect (même principe
// que le reste du projet : explicable, jamais une décision prise à la place de l'humain).
function asymmetryLabel(initiatorBytes: number, responderBytes: number): string {
  const total = initiatorBytes + responderBytes;
  if (total === 0) return "—";
  const initiatorPct = Math.round((initiatorBytes / total) * 100);
  return `${initiatorPct}% envoyé / ${100 - initiatorPct}% reçu`;
}

// describeAction : jamais le mot brut "Mixed" (demande de l'encadrant, 2026-09-06) --
// répartition chiffrée ("18 Allow / 2 Block") à la place, cf. theme/colors.ts.
function ActionChip({ action, allowCount, blockCount }: { action: string | null; allowCount: number; blockCount: number }) {
  if (!action) return null;
  const { label, color } = describeAction(action, allowCount, blockCount);
  return <Chip size="small" label={label} sx={{ backgroundColor: color, color: "#fff" }} />;
}

function CriticalityChip({ label }: { label: string | null }) {
  if (!label) return null;
  return <Chip size="small" label={displayAxisLabel(label)} sx={{ backgroundColor: criticalityColor(label), color: "#fff" }} />;
}

// Lecture seule (Matrice Validée, 2026-09-09) : ce Flow est reconstruit depuis un FlowSnapshot
// figé, pas l'état courant -- Valider/Bloquer/Changer la règle agiraient sur le Flow VIVANT
// sans que ça se reflète dans cette vue historique (qui ne change jamais après coup), trompeur.
// Juste le statut figé à l'instant de la clôture, jamais une action possible depuis ici.
function ReadOnlyValidationCell({ status }: { status: string }) {
  return (
    <Chip
      size="small"
      variant="outlined"
      label={STATUS_LABELS[status] ?? status}
      sx={{ borderColor: validationStatusColor(status), color: validationStatusColor(status) }}
    />
  );
}

function ValidationCell({
  flow,
  diffStatus,
  onRequestRuleChange,
}: {
  flow: FlowOut;
  // "Disparu" (2026-09-12, demande de l'encadrant) : informationnel uniquement, jamais une
  // action requise (décision déjà actée le 2026-08-21) -- incohérent de laisser
  // Valider/Bloquer/Changer la règle actifs dessus, ça prête à confusion sur ce qui
  // nécessite vraiment une revue. Optionnel : FlowsTable reste utilisable sans diff_status
  // (Table des flux, Matrice), où la notion même de "disparu" n'existe pas.
  diffStatus?: DiffStatus;
  onRequestRuleChange: (flow: FlowOut, targetAction: "Allow" | "Block") => void;
}) {
  const validateFlow = useValidateFlow();
  const disparu = diffStatus === "disparu";
  // Désactivés (pas masqués) : la ligne garde la même forme que les autres statuts de ce
  // même tableau -- un bouton qui apparaît/disparaît selon le statut serait lui-même une
  // source de confusion supplémentaire.
  const disabledReason = "Disparu : ce flux n'a pas été revu depuis la dernière clôture de cycle,aucune action requise.";

  // Valider/Bloquer : toujours un clic simple et immédiat, jamais de fenêtre (décision de
  // conception actée le 2026-09-05, après un test réel où la détection de contradiction ne
  // déclenchait la fenêtre dans aucun cas concret sur /validation-cycle) -- disparaissent une
  // fois la décision prise, remplacés par le chip de statut, comportement d'origine.
  return (
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
        <Tooltip title={disparu ? disabledReason : ""}>
          <span>
            <Button size="small" color="success" variant="outlined" disabled={disparu} loading={validateFlow.isPending} onClick={() => validateFlow.mutate({ flowId: flow.id, payload: { status: "approved" } })}>
              Valider
            </Button>
            <Button size="small" color="error" variant="outlined" disabled={disparu} loading={validateFlow.isPending} onClick={() => validateFlow.mutate({ flowId: flow.id, payload: { status: "blocked" } })} sx={{ ml: 1 }}>
              Bloquer
            </Button>
          </span>
        </Tooltip>
      )}
      {/* Bouton dédié "Changer la règle" -- toujours visible (sauf "disparu", ci-dessus),
          quel que soit le statut : SEUL déclencheur de la fenêtre de confirmation +
          justification + fiche PDF. */}
      <Tooltip title={disparu ? disabledReason : ""}>
        <span>
          <Button size="small" color="warning" variant="outlined" disabled={disparu} onClick={() => onRequestRuleChange(flow, invertedAction(flow))}>
            Changer la règle
          </Button>
        </span>
      </Tooltip>
    </Stack>
  );
}

export function FlowsTable({
  flows,
  showDiffColumn = false,
  onDiffClick,
  readOnly = false,
}: {
  flows: FlowWithDiff[];
  showDiffColumn?: boolean;
  onDiffClick?: (flow: FlowWithDiff) => void;
  // Matrice Validée (2026-09-09) : Flow reconstruits depuis un FlowSnapshot figé -- aucune
  // action de validation possible depuis cette vue historique, cf. ReadOnlyValidationCell.
  readOnly?: boolean;
}) {
  // Possédé par FlowsTable (composant stable), pas par la cellule de la ligne (recréée par AG
  // Grid à chaque invalidation de rowData -- bug réel constaté le 2026-09-05 où l'état de la
  // fenêtre disparaissait juste après confirmation, la mutation ayant elle-même déclenché le
  // remount de la cellule avant que le succès ne soit affiché).
  const [override, setOverride] = useState<{ flow: FlowOut; targetAction: "Allow" | "Block" } | null>(null);
  // Drill-down LogEntry (2026-09-06) -- même raisonnement que `override` ci-dessus : possédé
  // par FlowsTable, jamais par la cellule de la ligne.
  const [logEntriesFlow, setLogEntriesFlow] = useState<FlowOut | null>(null);

  const columnDefs = useMemo<ColDef<FlowWithDiff>[]>(
    () => [
      ...(showDiffColumn
        ? [
            {
              headerName: "Écart",
              width: 130,
              pinned: "left" as const,
              sortable: false,
              filter: false,
              cellRenderer: (p: { data?: FlowWithDiff }) => (p.data ? <DiffChip flow={p.data} onClick={onDiffClick} /> : null),
            },
          ]
        : []),
      { field: "src_ip", headerName: "Source", pinned: "left", width: 140 },
      { field: "dst_ip", headerName: "Destination", width: 140 },
      { field: "dst_port", headerName: "Port", width: 90 },
      { field: "protocol", headerName: "Protocole", width: 100 },
      {
        // showDiffColumn (Cycle de validation) : action de CE cycle (cycle_dominant_action),
        // jamais lifetime -- bug réel signalé le 2026-09-06 : dominant_action reste "Mixed"
        // pour toujours dès qu'une seule occurrence contradictoire a existé n'importe quand
        // dans l'histoire du flow, même hors de ce cycle. Table des flux/Matrice Réelle (pas
        // de cycle en jeu) gardent le lifetime, seule vue pertinente hors contexte de cycle.
        colId: "action",
        headerName: "Action",
        width: 110,
        // valueGetter ajouté (2026-09-11) -- sans ça, cette colonne n'avait aucune valeur
        // exploitable par le filtre (seul un cellRenderer était défini), le filtre par défaut
        // ne pouvait donc rien matcher. Même action brute que celle affichée par ActionChip.
        valueGetter: (p) => (p.data ? (showDiffColumn ? p.data.cycle_dominant_action : p.data.dominant_action) : ""),
        cellRenderer: (p: { data?: FlowOut }) =>
          p.data ? (
            <ActionChip
              action={showDiffColumn ? p.data.cycle_dominant_action : p.data.dominant_action}
              allowCount={showDiffColumn ? p.data.cycle_allow_count : p.data.allow_count}
              blockCount={showDiffColumn ? p.data.cycle_block_count : p.data.block_count}
            />
          ) : null,
      },
      {
        colId: "occurrences",
        headerName: "Occurrences",
        width: 130,
        cellStyle: { cursor: "pointer" },
        valueGetter: (p) => (p.data ? (showDiffColumn ? p.data.cycle_occurrence_count : p.data.occurrence_count) : ""),
        // Drill-down (2026-09-06, demande de l'encadrant) : occurrence_count agrège
        // potentiellement des milliers de connexions, jamais consultables une par une avant
        // ce panneau. Cliquable plutôt qu'un survol -- même principe déjà acté sur ce projet
        // (badge "Écart", boutons Valider/Bloquer) : ce qui s'ouvre au clic ne doit jamais se
        // deviner, ni se cacher derrière un tooltip discret.
        onCellClicked: (p) => p.data && setLogEntriesFlow(p.data),
      },
      {
        headerName: "Volume",
        width: 110,
        valueGetter: (p) =>
          p.data
            ? formatBytes(
                showDiffColumn
                  ? p.data.cycle_total_initiator_bytes + p.data.cycle_total_responder_bytes
                  : p.data.total_initiator_bytes + p.data.total_responder_bytes,
              )
            : "",
      },
      {
        headerName: "Asymétrie envoyé/reçu",
        width: 190,
        valueGetter: (p) =>
          p.data ? asymmetryLabel(p.data.total_initiator_bytes, p.data.total_responder_bytes) : "",
      },
      { field: "first_seen_at", headerName: "Première vue", width: 170 },
      { field: "last_seen_at", headerName: "Dernière vue", width: 170 },
      {
        headerName: "Application",
        width: 170,
        valueGetter: (p) => p.data?.web_application ?? p.data?.application_protocol ?? "",
        tooltipValueGetter: (p) => (p.value ? String(p.value) : undefined),
      },
      {
        field: "last_access_control_rule_name",
        headerName: "Règle ACL",
        width: 240,
        tooltipValueGetter: (p) => (p.value ? String(p.value) : undefined),
      },
      {
        colId: "criticality",
        headerName: "Criticité",
        width: 120,
        // valueGetter ajouté (2026-09-11) -- même raison que la colonne Action ci-dessus.
        valueGetter: (p) => p.data?.criticality_label ?? "",
        cellRenderer: (p: { data?: FlowOut }) => (p.data ? <CriticalityChip label={p.data.criticality_label} /> : null),
      },
      {
        colId: "validation",
        headerName: "Validation",
        // 420 (pas 200) : jusqu'à 3 boutons sur une ligne (Valider/Bloquer/Changer la règle)
        // -- bug réel constaté le 2026-09-05, "Changer la règle" existait dans le DOM mais
        // restait invisible, coupé par la hauteur de ligne fixe d'AG Grid après un retour à
        // la ligne forcé par une colonne trop étroite. readOnly : juste un chip, 140 suffit.
        width: readOnly ? 140 : 420,
        sortable: false,
        filter: false,
        cellStyle: undefined, // jamais le curseur "pointer" ici -- ne déclenche jamais l'ouverture du panneau
        cellRenderer: (p: { data?: FlowWithDiff }) =>
          p.data ? (
            readOnly ? (
              <ReadOnlyValidationCell status={p.data.validation_status} />
            ) : (
              <ValidationCell
                flow={p.data}
                diffStatus={p.data.diff_status}
                onRequestRuleChange={(flow, targetAction) => setOverride({ flow, targetAction })}
              />
            )
          ) : null,
      },
    ],
    [showDiffColumn, onDiffClick, readOnly],
  );

  // Toute la ligne ouvre le panneau de détail (bug réel signalé par Loulou, 2026-08-24 : seul
  // le petit badge "Écart" était cliquable, sans affordance visuelle sur le reste de la ligne
  // -- incohérent avec AclProposalsTable/RecommendationsTable, où onRowClicked couvre déjà
  // toute la ligne). Exclut Validation (Valider/Bloquer/Changer la règle) et Occurrences
  // (ouvre le drill-down LogEntry, cf. colDef ci-dessus) : cliquer dessus ne doit jamais
  // aussi ouvrir le panneau de diff.
  function handleCellClicked(event: CellClickedEvent<FlowWithDiff>) {
    if (!onDiffClick || !event.data) return;
    const colId = event.column.getColId();
    if (colId === "validation" || colId === "occurrences") return;
    onDiffClick(event.data);
  }

  return (
    <div style={{ height: 600, width: "100%" }}>
      <AgGridReact<FlowWithDiff>
        theme={appGridTheme}
        rowData={flows}
        columnDefs={columnDefs}
        // filter: SimpleColumnFilter (2026-09-11, demande de l'encadrant) remplace le filtre
        // par défaut d'AG Grid (menu "Contains/Equals/.../AND/OR") sur TOUTES les colonnes
        // filtrables -- un seul champ de recherche par colonne, appliqué sur Entrée, jamais de
        // condition à choisir. "Écart" et "Validation" gardent `filter: false` (badges/
        // boutons, pas du texte à chercher, cf. leurs colDef ci-dessus).
        defaultColDef={{ sortable: true, filter: SimpleColumnFilter, resizable: true, cellStyle: onDiffClick ? { cursor: "pointer" } : undefined }}
        pagination
        paginationPageSize={50}
        onCellClicked={onDiffClick ? handleCellClicked : undefined}
      />
      <ActionOverrideDialog flow={override?.flow ?? null} targetAction={override?.targetAction ?? null} onClose={() => setOverride(null)} />
      <FlowLogEntriesDrawer flow={logEntriesFlow} onClose={() => setLogEntriesFlow(null)} />
    </div>
  );
}

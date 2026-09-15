import { Fragment, useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import DownloadIcon from "@mui/icons-material/Download";
import { useValidationHistory } from "../hooks/useValidationHistory";
import { useSourceOptions } from "../hooks/useSourceOptions";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { KeywordSearchField } from "../components/common/KeywordSearchField";
import { ValidationHistoryDetailDrawer } from "../components/history/ValidationHistoryDetailDrawer";
import { api } from "../api/client";
import { STATUS_LABELS, ACTION_LABELS, IDENTITY_COLORS } from "../theme/colors";
import type { ChangeType, EntryType, FlowHistoryEntryOut, ValidationHistoryEntryOut } from "../api/types";

// Regroupement visuel par jour (2026-09-12, demande de l'encadrant après démo) -- items déjà
// triés du plus récent au plus ancien côté backend (created_at DESC, fusion flux/politiques de
// sous-réseau incluse depuis le 2026-09-13), donc un simple passage séquentiel suffit à
// détecter un changement de jour, jamais un vrai regroupement/tri à faire ici. Clé de jour en
// heure locale (toLocaleDateString), pas un découpage UTC brut.
function dayKey(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR");
}

function dayHeading(iso: string): string {
  const label = new Date(iso).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return label.charAt(0).toUpperCase() + label.slice(1); // "vendredi 12..." -> "Vendredi 12..."
}

const CHANGE_TYPE_OPTIONS: { value: ChangeType; label: string }[] = [
  { value: "rule_change", label: "Changement de règle (avec justification)" },
  { value: "classic", label: "Validation classique (Valider/Bloquer)" },
];

// Badge "Flux"/"Sous-réseau" (2026-09-13, demande de l'encadrant : une politique de
// sous-réseau est aussi une vraie décision à tracer, au même titre qu'un changement de règle
// sur un flux précis) -- mêmes tokens IDENTITY_COLORS que les autres catégories sans gravité
// (finding_type, intent ACL), jamais une nouvelle palette inventée ici.
const ENTRY_TYPE_LABELS: Record<EntryType, string> = { flow: "Flux", network_policy: "Sous-réseau" };
const ENTRY_TYPE_COLORS: Record<EntryType, string> = { flow: IDENTITY_COLORS.blue, network_policy: IDENTITY_COLORS.violet };

const ENTRY_TYPE_OPTIONS: { value: EntryType; label: string }[] = [
  { value: "flow", label: ENTRY_TYPE_LABELS.flow },
  { value: "network_policy", label: ENTRY_TYPE_LABELS.network_policy },
];

export function HistoryPage() {
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [changeType, setChangeType] = useState<ChangeType | "">("");
  const [entryType, setEntryType] = useState<EntryType | "">("");
  // FlowHistoryEntryOut uniquement -- une ligne "Sous-réseau" ne s'ouvre jamais dans ce
  // panneau (tous ses champs sont déjà visibles directement dans le tableau ci-dessous).
  const [selectedEntry, setSelectedEntry] = useState<FlowHistoryEntryOut | null>(null);

  const sourceOptions = useSourceOptions();
  const { data, isLoading, isError, error } = useValidationHistory({
    q,
    source: source || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    // "Type de changement" est un concept propre au flux (rule_change/classic) -- une
    // politique de sous-réseau n'est ni l'un ni l'autre (backend/app/validation_history_query
    // .py) : sans intérêt, et silencieusement vidé de résultats, si "Sous-réseau" est
    // sélectionné en même temps -- masqué du tout dans ce cas (cf. JSX plus bas).
    changeType: entryType === "network_policy" ? undefined : changeType || undefined,
    entryType: entryType || undefined,
  });

  const hasAnyFilter = !!q || !!source || !!dateFrom || !!dateTo || !!changeType || !!entryType;

  function resetFilters() {
    setQ("");
    setSource("");
    setDateFrom("");
    setDateTo("");
    setChangeType("");
    setEntryType("");
  }

  function handleRowClick(entry: ValidationHistoryEntryOut) {
    if (entry.entry_type === "flow") setSelectedEntry(entry);
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Historique des validations
      </Typography>

      {/* Filtres (2026-09-12, demande de l'encadrant après démo) -- même emplacement/style que
          les autres pages (Table des flux, Cycle de validation) : une ligne sous le titre,
          Source d'abord (même sélecteur partagé), puis plage de dates, type de changement, et
          la recherche par mot-clé déjà existante en dernier. "Type" (2026-09-13) juste après
          Source -- distinction Flux/Sous-réseau plus fondamentale que "Type de changement",
          qui affine seulement à l'intérieur des flux. */}
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center", mb: 2 }}>
        <TextField select size="small" label="Source (firewall)" value={source} onChange={(e) => setSource(e.target.value)} sx={{ minWidth: 200 }}>
          <MenuItem value="">Toutes les sources</MenuItem>
          {sourceOptions.map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Type"
          value={entryType}
          onChange={(e) => setEntryType(e.target.value as EntryType | "")}
          sx={{ minWidth: 170 }}
        >
          <MenuItem value="">Tous</MenuItem>
          {ENTRY_TYPE_OPTIONS.map((opt) => (
            <MenuItem key={opt.value} value={opt.value}>
              {opt.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Du"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ width: 160 }}
        />
        <TextField
          size="small"
          label="Au"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ width: 160 }}
        />
        {entryType !== "network_policy" && (
          <TextField
            select
            size="small"
            label="Type de changement"
            value={changeType}
            onChange={(e) => setChangeType(e.target.value as ChangeType | "")}
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="">Tous</MenuItem>
            {CHANGE_TYPE_OPTIONS.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>
                {opt.label}
              </MenuItem>
            ))}
          </TextField>
        )}
        <KeywordSearchField value={q} onChange={setQ} />
        {hasAnyFilter && (
          <Button size="small" color="secondary" onClick={resetFilters}>
            Réinitialiser
          </Button>
        )}
      </Stack>

      {isLoading && <TableSkeleton />}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data && data.items.length === 0 && hasAnyFilter && (
        <Alert severity="info">Aucune validation ne correspond à ces filtres.</Alert>
      )}
      {data && data.items.length === 0 && !hasAnyFilter && (
        <Alert severity="info">Aucune validation enregistrée pour l'instant.</Alert>
      )}

      {data && data.items.length > 0 && (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {data.total_count} changement(s) de statut enregistré(s)
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Type</TableCell>
                <TableCell>Date</TableCell>
                <TableCell>Source</TableCell>
                <TableCell>Flux</TableCell>
                <TableCell>Changement</TableCell>
                <TableCell>Décidé par</TableCell>
                <TableCell>Justification</TableCell>
                <TableCell>Fiche</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.items.map((entry, i) => {
                const previous = data.items[i - 1];
                const showDayHeading = !previous || dayKey(previous.created_at) !== dayKey(entry.created_at);
                const isFlow = entry.entry_type === "flow";
                return (
                  <Fragment key={`${entry.entry_type}-${entry.id}`}>
                    {showDayHeading && (
                      <TableRow>
                        <TableCell colSpan={8} sx={{ backgroundColor: "action.hover", fontWeight: 600, py: 0.75 }}>
                          {dayHeading(entry.created_at)}
                        </TableCell>
                      </TableRow>
                    )}
                    <TableRow hover={isFlow} sx={{ cursor: isFlow ? "pointer" : "default" }} onClick={() => handleRowClick(entry)}>
                      <TableCell>
                        <Chip
                          size="small"
                          label={ENTRY_TYPE_LABELS[entry.entry_type]}
                          sx={{ backgroundColor: ENTRY_TYPE_COLORS[entry.entry_type], color: "#fff" }}
                        />
                      </TableCell>
                      <TableCell>{new Date(entry.created_at).toLocaleTimeString("fr-FR")}</TableCell>
                      <TableCell>{entry.source ?? "—"}</TableCell>
                      <TableCell>
                        {isFlow ? (
                          <>
                            {entry.src_ip} → {entry.dst_ip}
                            {entry.dst_port !== null ? `:${entry.dst_port}` : ""} ({entry.protocol})
                          </>
                        ) : (
                          <>
                            {entry.src_cidr} → {entry.destination}
                          </>
                        )}
                      </TableCell>
                      <TableCell>
                        {isFlow ? (
                          <>
                            {entry.old_status ? (STATUS_LABELS[entry.old_status] ?? entry.old_status) : "—"} → {STATUS_LABELS[entry.new_status] ?? entry.new_status}
                          </>
                        ) : (
                          ACTION_LABELS[entry.action] ?? entry.action
                        )}
                      </TableCell>
                      <TableCell>{entry.decided_by ?? "—"}</TableCell>
                      <TableCell sx={{ maxWidth: 220 }}>{entry.justification ?? "—"}</TableCell>
                      <TableCell>
                        {isFlow && entry.justification && (
                          <Button
                            size="small"
                            startIcon={<DownloadIcon />}
                            component="a"
                            href={api.actionChangeFicheUrl(entry.id)}
                            download
                            onClick={(e) => e.stopPropagation()} // ne doit jamais aussi ouvrir le panneau
                          >
                            Télécharger
                          </Button>
                        )}
                        {!isFlow && (
                          <Button
                            size="small"
                            startIcon={<DownloadIcon />}
                            component="a"
                            href={api.networkPolicyFicheUrl(entry.id)}
                            download
                          >
                            Télécharger
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </>
      )}

      <ValidationHistoryDetailDrawer entry={selectedEntry} onClose={() => setSelectedEntry(null)} />
    </Box>
  );
}

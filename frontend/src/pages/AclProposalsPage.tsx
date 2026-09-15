import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import { useAclProposals, useRunAclProposals } from "../hooks/useAclProposals";
import { AclProposalsTable } from "../components/acl-proposals/AclProposalsTable";
import { INTENT_LABELS, STATUS_LABELS } from "../theme/colors";
import { AclProposalsLegend } from "../components/acl-proposals/AclProposalsLegend";
import { AclProposalDetailDrawer } from "../components/acl-proposals/AclProposalDetailDrawer";
import { ManualAclProposalForm } from "../components/acl-proposals/ManualAclProposalForm";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { KeywordSearchField } from "../components/common/KeywordSearchField";
import type { AclProposalFilters, AclProposalOut } from "../api/types";

const STATUS_OPTIONS = ["pending", "approved", "rejected"];

export function AclProposalsPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<AclProposalFilters>({ status: "pending" });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [manualFormOpen, setManualFormOpen] = useState(false);
  const [showManualRun, setShowManualRun] = useState(false);
  const [q, setQ] = useState("");

  const { data, isLoading, isError, error } = useAclProposals({ ...filters, q });
  const runAclProposals = useRunAclProposals();
  const selected = data?.items.find((p) => p.id === selectedId) ?? null;

  function set<K extends keyof AclProposalFilters>(key: K, raw: string) {
    setFilters({ ...filters, [key]: raw === "" ? undefined : raw });
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Propositions ACL
      </Typography>

      <AclProposalsLegend />

      <Alert severity="info" sx={{ mb: 2 }}>
        Les propositions se génèrent maintenant depuis le <strong>Cycle de validation</strong>,
        <Button size="small" onClick={() => navigate("/validation-cycle")}>
          Aller au Cycle de validation
        </Button>
      </Alert>

      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center", mb: 2 }}>
        <TextField
          select
          size="small"
          label="Statut"
          value={filters.status ?? ""}
          onChange={(e) => set("status", e.target.value)}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">Tous</MenuItem>
          {STATUS_OPTIONS.map((s) => (
            <MenuItem key={s} value={s}>
              {STATUS_LABELS[s] ?? s}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          size="small"
          label="Type"
          value={filters.intent ?? ""}
          onChange={(e) => set("intent", e.target.value)}
          sx={{ minWidth: 170 }}
        >
          <MenuItem value="">Tous</MenuItem>
          {Object.entries(INTENT_LABELS).map(([intent, label]) => (
            <MenuItem key={intent} value={intent}>
              {label}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          size="small"
          label="Source (site)"
          value={filters.source ?? ""}
          onChange={(e) => set("source", e.target.value)}
          sx={{ minWidth: 160 }}
        />

        <Button variant="outlined" size="small" onClick={() => setManualFormOpen(true)}>
          Ajouter une proposition manuelle
        </Button>

        <KeywordSearchField value={q} onChange={setQ} />
      </Stack>

      {!showManualRun ? (
        <Button size="small" color="secondary" sx={{ mb: 2 }} onClick={() => setShowManualRun(true)}>
          Relance manuelle sur tout l'historique (avancé)
        </Button>
      ) : (
        <Stack direction="row" spacing={2} sx={{ mb: 2, alignItems: "center" }}>
          <Button variant="outlined" size="small" loading={runAclProposals.isPending} onClick={() => runAclProposals.mutate()}>
            Lancer la génération (tout l'historique, hors cycle)
          </Button>
          <Typography variant="caption" color="text.secondary">
            À réserver à une reprise/dépannage -- ignore le scoping par cycle, reconsidère tout
            l'historique approuvé/acquitté de toutes sources.
          </Typography>
        </Stack>
      )}

      {runAclProposals.isSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => runAclProposals.reset()}>
          Génération terminée : {runAclProposals.data.total_proposals} proposition(s) au total (
          {runAclProposals.data.created} créée(s), {runAclProposals.data.updated} mise(s) à jour) --{" "}
          create: {runAclProposals.data.by_intent.create ?? 0}, tighten: {runAclProposals.data.by_intent.tighten ?? 0}, revoke:{" "}
          {runAclProposals.data.by_intent.revoke ?? 0}.
          <br />
          "create" en détail : {runAclProposals.data.create_detail.considered} flux approuvé(s) pris en compte,{" "}
          {runAclProposals.data.create_detail.already_covered} déjà couvert(s) par une règle explicite (rien à créer),{" "}
          {runAclProposals.data.create_detail.eligible} éligible(s) à une nouvelle règle.
        </Alert>
      )}
      {runAclProposals.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {(runAclProposals.error as Error).message}
        </Alert>
      )}

      {isLoading && <TableSkeleton />}
      {isError && <Alert severity="error">{(error as Error).message}</Alert>}

      {data && data.items.length === 0 && q && (
        <Alert severity="info">Aucune proposition ne correspond à "{q}".</Alert>
      )}
      {data && data.items.length === 0 && !q && (
        <Alert severity="info">
          Aucune proposition pour ces filtres -- lance une génération si aucune n'a encore été
          exécutée, élargis le filtre de statut, ou ajoute une proposition manuelle.
        </Alert>
      )}

      {data && data.items.length > 0 && (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {data.total_count} proposition(s)
          </Typography>
          <AclProposalsTable items={data.items} onRowClicked={(p: AclProposalOut) => setSelectedId(p.id)} />
        </>
      )}

      <AclProposalDetailDrawer proposal={selected} onClose={() => setSelectedId(null)} />
      <ManualAclProposalForm open={manualFormOpen} onClose={() => setManualFormOpen(false)} />
    </Box>
  );
}

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Divider from "@mui/material/Divider";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import { FileDropZone } from "../components/import/FileDropZone";
import { ImportErrorsDialog } from "../components/import/ImportErrorsDialog";
import { useImportLogs, useImportHistory } from "../hooks/useImportLogs";
import { useQualifyFlows } from "../hooks/useFlows";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { STATUS_COLORS } from "../theme/colors";

// Étapes 1 (import) à 2 (qualification) de docs/12-checklist-apres-import.md, enchaînées dans
// cette page -- bouton dédié affiché progressivement, jamais déclenché automatiquement (même
// principe que Recommandations/Propositions ACL : un clic explicite par moteur). L'étape 3
// (recommandations) retirée d'ici le 2026-09-12 (demande de l'encadrant, même mise en
// sourdine que partout ailleurs, ce point d'entrée avait été oublié) -- voir le commentaire
// juste avant la carte "Étape suivante : qualification" plus bas pour la restauration. Les
// étapes 4 (revue humaine) et 5 (Propositions ACL) ne peuvent de toute façon pas être
// enchaînées ici : elles dépendent d'une décision humaine sur des flux/findings précis, pas
// d'un simple "suivant".
export function ImportPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const importLogs = useImportLogs();
  const qualifyFlows = useQualifyFlows();
  // Historique des imports (2026-09-11, demande de l'encadrant) -- INDÉPENDANT de l'état de
  // importLogs (la mutation d'upload) ci-dessus : c'est ce qui lui permet de rester visible
  // même après avoir navigué ailleurs et être revenu sur cette page (voir plus bas).
  const importHistory = useImportHistory();
  // Détail des erreurs de parsing (2026-09-14, demande de l'encadrant) -- id de l'import
  // dont on veut voir le détail, `null` = boîte de dialogue fermée. Voir ImportErrorsDialog.tsx.
  const [errorsDialogImportLogId, setErrorsDialogImportLogId] = useState<number | null>(null);

  function handleFileSelected(selected: File) {
    setFile(selected);
    importLogs.mutate(selected);
  }

  function reset() {
    setFile(null);
    importLogs.reset();
    qualifyFlows.reset();
  }

  const uploading = importLogs.isPending && importLogs.uploadProgress !== null && importLogs.uploadProgress < 100;
  const processing = importLogs.isPending && !uploading;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 1 }}>
        Import de logs
      </Typography>
      
      {!importLogs.isSuccess && (
        <Card variant="outlined" sx={{ maxWidth: 640 }}>
          <CardContent>
            <FileDropZone onFileSelected={handleFileSelected} disabled={importLogs.isPending} />

            {uploading && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" sx={{ mb: 0.5 }}>
                  Envoi de {file?.name} -- {importLogs.uploadProgress}%
                </Typography>
                <LinearProgress variant="determinate" value={importLogs.uploadProgress ?? 0} />
              </Box>
            )}

            {processing && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" sx={{ mb: 0.5 }}>
                  Traitement en cours...peut prendre plusieurs minutes pour un fichier volumineux
                </Typography>
                <LinearProgress />
              </Box>
            )}

            {importLogs.isError && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {(importLogs.error as Error).message}
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      {importLogs.isSuccess && importLogs.data && (
        <Stack spacing={2} sx={{ maxWidth: 640 }}>
          {/* Simplifié (2026-09-09, demande de l'encadrant) : une confirmation simple pour
              l'utilisateur final, jamais le détail chiffré ici -- retiré le 2026-09-12
              (demande de l'encadrant) : le détail complet (lignes lues, entrées créées,
              doublons, erreurs, flux touchés, source(s)) est désormais uniquement dans
              "Historique des imports" plus bas sur cette même page, pas dupliqué ici.
              ImportSummary (backend) reste inchangé, toujours utile pour les tests/logs
              internes. */}
          <Alert severity="success" icon={<CheckCircleOutlineIcon fontSize="inherit" />}>
            Import réussi :{importLogs.data.filename}
          </Alert>

          {/* Une erreur de parsing reste signalée même dans la vue simplifiée -- ce n'est pas
              un détail secondaire mais une vraie anomalie (des lignes n'ont pas pu être
              analysées), jamais masquée silencieusement. */}
          {importLogs.data.parsing_errors > 0 && (
            <Alert severity="warning">
              {importLogs.data.parsing_errors} ligne(s) n'ont pas pu être analysée(s) -- cliquez
              sur le nombre d'erreurs dans "Historique des imports" plus bas pour voir le détail
              (ligne brute et raison exacte).
            </Alert>
          )}

          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
                Étape suivante : qualification
              </Typography>

              {!qualifyFlows.isSuccess && (
                <Button variant="contained" size="small" loading={qualifyFlows.isPending} onClick={() => qualifyFlows.mutate()}>
                  Lancer la qualification
                </Button>
              )}
              {qualifyFlows.isError && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {(qualifyFlows.error as Error).message}
                </Alert>
              )}

              {qualifyFlows.isSuccess && qualifyFlows.data && (
                <>
                  <Alert severity="success">
                    {qualifyFlows.data.total_qualified} flux qualifié(s) :{" "}
                    {Object.entries(qualifyFlows.data.label_counts)
                      .map(([label, count]) => `${label} : ${count}`)
                      .join(", ")}
                    .
                  </Alert>

                  {qualifyFlows.data.unclassified_zones.length > 0 && (
                    <Alert severity="warning" sx={{ mt: 1 }}>
                      Zones non classées détectées : {qualifyFlows.data.unclassified_zones.join(", ")}
                      . Score de criticité calculé par défaut pour ces flux (rôle interne/externe
                      inconnu) -- à vérifier avant de considérer les résultats "high"/"critical" de
                      cette source comme fiables.
                    </Alert>
                  )}

                  {/* "Étape suivante : recommandations" retirée le 2026-09-12 (demande de
                      l'encadrant) -- le Recommendation Engine est mis en sourdine partout
                      ailleurs dans l'app (Sidebar.tsx, docs/perspectives.md) depuis le
                      2026-09-03/04 ; ce bouton était resté un point d'entrée UI oublié malgré
                      ça, même situation que le bouton ACL retiré de ValidationCyclePage.tsx le
                      2026-09-10. AUCUN code/endpoint/modèle/test lié au Recommendation Engine
                      supprimé -- hooks/useRecommendations.ts, Services/recommendation_engine.py,
                      RecommendationsPage.tsx (route directe /recommendations) restent intacts,
                      pour une réactivation immédiate si besoin : restaurer ici la Divider +
                      Typography "Étape suivante : recommandations" + le bouton "Lancer les
                      recommandations" (useRunRecommendations(), cf. historique git). */}
                </>
              )}
            </CardContent>
          </Card>

          <Button size="small" onClick={reset} sx={{ alignSelf: "flex-start" }}>
            Importer un autre fichier
          </Button>
        </Stack>
      )}

      {/* Historique des imports (2026-09-11, demande de l'encadrant) -- rendu
          INCONDITIONNELLEMENT, hors des deux blocs ci-dessus pilotés par l'état de la
          mutation d'upload en cours : c'est précisément ce qui le fait disparaître dès qu'on
          quitte la page aujourd'hui. Alimenté par sa propre requête (useImportHistory),
          toutes sources confondues, triée du plus récent au plus ancien côté backend. */}
      <Divider sx={{ my: 3, maxWidth: 900 }} />
      <Typography variant="h6" sx={{ mb: 1 }}>
        Historique des imports
      </Typography>

      {importHistory.isLoading && <TableSkeleton rows={4} />}
      {importHistory.isError && (
        <Alert severity="error" sx={{ maxWidth: 900 }}>
          {(importHistory.error as Error).message}
        </Alert>
      )}
      {importHistory.data && importHistory.data.items.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Aucun import pour l'instant.
        </Typography>
      )}
      {importHistory.data && importHistory.data.items.length > 0 && (
        <Table size="small" sx={{ maxWidth: 900 }}>
          <TableHead>
            <TableRow>
              <TableCell>Fichier</TableCell>
              <TableCell>Source(s)</TableCell>
              <TableCell>Date</TableCell>
              <TableCell>Lignes lues</TableCell>
              <TableCell>Entrées créées</TableCell>
              <TableCell>Doublons ignorés</TableCell>
              <TableCell>Erreurs de parsing</TableCell>
              <TableCell>Flux touchés</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {importHistory.data.items.map((log) => (
              <TableRow key={log.id}>
                <TableCell>{log.filename}</TableCell>
                <TableCell>{log.source}</TableCell>
                <TableCell>{new Date(log.imported_at).toLocaleString("fr-FR")}</TableCell>
                <TableCell>{log.lines_read}</TableCell>
                <TableCell>{log.log_entries_created}</TableCell>
                <TableCell>{log.log_entries_skipped_duplicate}</TableCell>
                <TableCell
                  sx={{
                    color: log.parsing_errors > 0 ? STATUS_COLORS.serious : undefined,
                    cursor: log.parsing_errors > 0 ? "pointer" : undefined,
                    textDecoration: log.parsing_errors > 0 ? "underline" : undefined,
                  }}
                  onClick={log.parsing_errors > 0 ? () => setErrorsDialogImportLogId(log.id) : undefined}
                >
                  {log.parsing_errors}
                </TableCell>
                <TableCell>{log.flows_touched}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <ImportErrorsDialog
        importLogId={errorsDialogImportLogId}
        filename={importHistory.data?.items.find((log) => log.id === errorsDialogImportLogId)?.filename}
        onClose={() => setErrorsDialogImportLogId(null)}
      />
    </Box>
  );
}

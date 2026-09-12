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
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import { FileDropZone } from "../components/import/FileDropZone";
import { useImportLogs, useImportHistory } from "../hooks/useImportLogs";
import { useQualifyFlows } from "../hooks/useFlows";
import { useRunRecommendations } from "../hooks/useRecommendations";
import { TableSkeleton } from "../components/common/TableSkeleton";
import { STATUS_COLORS } from "../theme/colors";

// Étapes 1 (import) à 3 (recommandations) de docs/12-checklist-apres-import.md, enchaînées
// dans cette page -- boutons dédiés affichés progressivement, jamais déclenchés
// automatiquement (même principe que Recommandations/Propositions ACL : un clic explicite
// par moteur). L'étape 4 (revue humaine) et 5 (Propositions ACL) ne peuvent pas être
// enchaînées ici : elles dépendent d'une décision humaine sur des flux/findings précis,
// pas d'un simple "suivant".
export function ImportPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [showImportDetail, setShowImportDetail] = useState(false);
  const importLogs = useImportLogs();
  const qualifyFlows = useQualifyFlows();
  const runRecommendations = useRunRecommendations();
  // Historique des imports (2026-09-11, demande de l'encadrant) -- INDÉPENDANT de l'état de
  // importLogs (la mutation d'upload) ci-dessus : c'est ce qui lui permet de rester visible
  // même après avoir navigué ailleurs et être revenu sur cette page (voir plus bas).
  const importHistory = useImportHistory();

  function handleFileSelected(selected: File) {
    setFile(selected);
    importLogs.mutate(selected);
  }

  function reset() {
    setFile(null);
    setShowImportDetail(false);
    importLogs.reset();
    qualifyFlows.reset();
    runRecommendations.reset();
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
              l'utilisateur final, jamais le détail chiffré par défaut -- ImportSummary
              (backend) reste inchangé, toujours utile pour les tests/logs internes, le détail
              complet reste consultable derrière "Voir le détail" juste en dessous. */}
          <Alert severity="success" icon={<CheckCircleOutlineIcon fontSize="inherit" />}>
            Import réussi :{importLogs.data.filename}
          </Alert>

          {/* Une erreur de parsing reste signalée même dans la vue simplifiée -- ce n'est pas
              un détail secondaire mais une vraie anomalie (des lignes n'ont pas pu être
              analysées), jamais masquée silencieusement. */}
          {importLogs.data.parsing_errors > 0 && (
            <Alert severity="warning">
              {importLogs.data.parsing_errors} ligne(s) n'ont pas pu être analysée(s) -- voir le
              détail ci-dessous.
            </Alert>
          )}

          <Button size="small" onClick={() => setShowImportDetail((v) => !v)} sx={{ alignSelf: "flex-start" }}>
            {showImportDetail ? "Masquer le détail" : "Voir le détail"}
          </Button>
          {showImportDetail && (
            <Stack spacing={0.5}>
              <Typography variant="body2">{importLogs.data.lines_read} ligne(s) lue(s)</Typography>
              <Typography variant="body2">{importLogs.data.log_entries_created} entrée(s) créée(s)</Typography>
              <Typography variant="body2">
                {importLogs.data.log_entries_skipped_duplicate} doublon(s) ignoré(s)
              </Typography>
              <Typography variant="body2" sx={{ color: importLogs.data.parsing_errors > 0 ? STATUS_COLORS.serious : undefined }}>
                {importLogs.data.parsing_errors} erreur(s) de parsing
              </Typography>
              <Typography variant="body2">{importLogs.data.flows_touched} flux touché(s)</Typography>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", mt: 0.5 }}>
                <Typography variant="body2">Source(s) :</Typography>
                {importLogs.data.sources.map((s) => (
                  <Chip
                    key={s}
                    size="small"
                    label={importLogs.data!.new_sources.includes(s) ? `${s} (nouvelle)` : s}
                    color={importLogs.data!.new_sources.includes(s) ? "primary" : "default"}
                    variant={importLogs.data!.new_sources.includes(s) ? "filled" : "outlined"}
                  />
                ))}
              </Stack>
            </Stack>
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

                  <Divider sx={{ my: 2 }} />

                  <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
                    Étape suivante : recommandations
                  </Typography>

                  {!runRecommendations.isSuccess && (
                    <Button
                      variant="contained"
                      size="small"
                      loading={runRecommendations.isPending}
                      onClick={() => runRecommendations.mutate()}
                    >
                      Lancer les recommandations
                    </Button>
                  )}
                  {runRecommendations.isError && (
                    <Alert severity="error" sx={{ mt: 2 }}>
                      {(runRecommendations.error as Error).message}
                    </Alert>
                  )}

                  {/* {runRecommendations.isSuccess && runRecommendations.data && (
                    <>
                      <Alert severity="success">
                        {runRecommendations.data.total_findings} recommandation(s) ({runRecommendations.data.created} créée(s),{" "}
                        {runRecommendations.data.updated} mise(s) à jour).
                      </Alert>

                      <Divider sx={{ my: 2 }} />

                      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                        Étape suivante (checklist) : revue humaine -- Valider des flux (Table des flux) et Traiter des
                        recommandations (Recommandations) -- avant de pouvoir lancer les Propositions ACL.
                      </Typography>
                      <Stack direction="row" spacing={1}>
                        <Button size="small" variant="outlined" onClick={() => navigate("/flows")}>
                          Aller à la Table des flux
                        </Button>
                        <Button size="small" variant="outlined" onClick={() => navigate("/recommendations")}>
                          Aller aux Recommandations
                        </Button>
                      </Stack>
                    </>
                  )} */}
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
                <TableCell sx={{ color: log.parsing_errors > 0 ? STATUS_COLORS.serious : undefined }}>
                  {log.parsing_errors}
                </TableCell>
                <TableCell>{log.flows_touched}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Box>
  );
}

import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import { useImportLogErrors } from "../../hooks/useImportLogs";
import { TableSkeleton } from "../common/TableSkeleton";

// Détail des lignes en échec de parsing d'un import précis (2026-09-14, demande de
// l'encadrant) -- ouvert en cliquant sur le nombre d'erreurs de la page Import : jusqu'ici
// seulement compté, sans moyen de voir QUELLE ligne ni POURQUOI, malgré la promesse du
// bandeau d'avertissement ("voir Historique des imports pour le détail"). Utile pour juger
// si une erreur isolée est bénigne ou révèle un vrai problème de format.
interface ImportErrorsDialogProps {
  importLogId: number | null;
  filename?: string;
  onClose: () => void;
}

export function ImportErrorsDialog({ importLogId, filename, onClose }: ImportErrorsDialogProps) {
  const { data, isLoading, isError, error } = useImportLogErrors(importLogId);

  return (
    <Dialog open={importLogId !== null} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        Erreurs de parsing
        {filename && (
          <Typography variant="body2" color="text.secondary">
            {filename}
          </Typography>
        )}
      </DialogTitle>
      <DialogContent>
        {isLoading && <TableSkeleton rows={4} />}
        {isError && <Alert severity="error">{(error as Error).message}</Alert>}
        {data && data.items.length === 0 && (
          <Alert severity="info">Aucune erreur enregistrée pour cet import.</Alert>
        )}
        {data && data.items.length > 0 && (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {data.items.length} ligne(s) ignorée(s) -- ligne brute et raison exacte du
              parser, pour juger si c'est bénin ou révèle un vrai problème de format.
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Ligne</TableCell>
                  <TableCell>Contenu brut</TableCell>
                  <TableCell>Erreur</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.items.map((err) => (
                  <TableRow key={err.id}>
                    <TableCell>{err.line_number}</TableCell>
                    <TableCell sx={{ maxWidth: 400, fontFamily: "monospace", fontSize: 12, wordBreak: "break-all" }}>
                      {err.raw_line}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 250 }}>{err.error_message}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Fermer</Button>
      </DialogActions>
    </Dialog>
  );
}

import Stack from "@mui/material/Stack";
import Skeleton from "@mui/material/Skeleton";

// Silhouette de chargement partagée par les 5 tableaux de l'app -- remplace le
// CircularProgress générique par une forme qui rappelle déjà le tableau à venir (colonnes +
// lignes), cohérent avec "silhouettes grises animées" plutôt qu'un simple spinner.
export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <Stack spacing={0.5}>
      <Skeleton variant="rounded" height={40} />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} variant="rounded" height={36} sx={{ opacity: 1 - i * 0.06 }} />
      ))}
    </Stack>
  );
}

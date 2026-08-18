import Stack from "@mui/material/Stack";
import Skeleton from "@mui/material/Skeleton";

export function StatCardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap" }}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} variant="rounded" width={150} height={72} />
      ))}
    </Stack>
  );
}

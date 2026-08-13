import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { FlowFilterValues } from "../api/types";

export function useMatrix(dimension = "zone", filters: FlowFilterValues = {}) {
  return useQuery({
    queryKey: ["matrix", dimension, filters],
    queryFn: () => api.getMatrix(dimension, filters),
  });
}

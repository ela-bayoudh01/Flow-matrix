import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { RecommendationFilters, RecommendationReview } from "../api/types";

export function useRecommendations(filters: RecommendationFilters) {
  return useQuery({
    queryKey: ["recommendations", filters],
    queryFn: () => api.getRecommendations(filters),
  });
}

export function useRunRecommendations() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.runRecommendations(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

export function useReviewRecommendation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: RecommendationReview }) =>
      api.reviewRecommendation(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

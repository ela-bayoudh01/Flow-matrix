import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AclProposalFilters, AclProposalManualCreate, AclProposalReview } from "../api/types";

export function useAclProposals(filters: AclProposalFilters) {
  return useQuery({
    queryKey: ["acl-proposals", filters],
    queryFn: () => api.getAclProposals(filters),
  });
}

export function useRunAclProposals() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.runAclProposals(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["acl-proposals"] });
    },
  });
}

export function useReviewAclProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AclProposalReview }) => api.reviewAclProposal(id, payload),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["acl-proposals"] });
      queryClient.invalidateQueries({ queryKey: ["acl-proposal-history", variables.id] });
    },
  });
}

export function useCreateManualAclProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AclProposalManualCreate) => api.createManualAclProposal(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["acl-proposals"] });
    },
  });
}

export function useAclProposalHistory(aclProposalId: number | null) {
  return useQuery({
    queryKey: ["acl-proposal-history", aclProposalId],
    queryFn: () => api.getAclProposalHistory({ aclProposalId: aclProposalId ?? undefined }),
    enabled: aclProposalId !== null,
  });
}

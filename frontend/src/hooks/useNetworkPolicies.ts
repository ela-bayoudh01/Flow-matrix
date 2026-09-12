import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { NetworkPolicyCreate } from "../api/types";

// Politiques de sous-réseau (2026-09-10) -- fonctionnalité isolée, voir api/types.ts.

export function useObservedSubnets(source: string, prefixLength: number) {
  return useQuery({
    queryKey: ["observed-subnets", source, prefixLength],
    queryFn: () => api.getObservedSubnets(source, prefixLength),
    enabled: !!source,
  });
}

export function useCreateNetworkPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: NetworkPolicyCreate) => api.createNetworkPolicy(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["network-policies"] });
    },
  });
}

export function useNetworkPolicies(source?: string) {
  return useQuery({
    queryKey: ["network-policies", source],
    queryFn: () => api.getNetworkPolicies({ source, limit: 200 }),
  });
}

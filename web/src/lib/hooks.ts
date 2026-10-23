import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type AppState, type Company, type Profile, type SentRow, type Watch } from "./api";

export const useAppState = () => useQuery({ queryKey: ["state"], queryFn: () => api.get<AppState>("/state") });
export const useCompanies = () => useQuery({ queryKey: ["companies"], queryFn: () => api.get<Company[]>("/companies") });
export const useWatchlist = () => useQuery({ queryKey: ["watchlist"], queryFn: () => api.get<Watch[]>("/watchlist") });
export const useHistory = () => useQuery({ queryKey: ["history"], queryFn: () => api.get<SentRow[]>("/history") });

/** A mutation that refreshes all data afterwards and shows errors as toasts. */
export function useAction<TVars, TResult = unknown>(fn: (vars: TVars) => Promise<TResult>, success?: string | ((r: TResult) => string)) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result) => {
      qc.invalidateQueries();
      if (success) toast.success(typeof success === "function" ? success(result) : success);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useSaveProfile() {
  return useAction((p: Partial<Profile>) => api.put<AppState>("/profile", p), "Saved");
}

export const timeAgo = (iso: string | null) => {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
};

export const daysSince = (iso: string) => Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);

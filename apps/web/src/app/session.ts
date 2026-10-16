import { useQuery } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api";

export type Role = "merchant" | "operator" | "admin";

export type SessionAccount = {
  id: string;
  role: Role;
  display_name: string;
};

/**
 * One query per app lifetime: the server identifies the account from the HttpOnly cookie,
 * so the SPA never carries identity in state. On 401 we return `null` so guards redirect.
 */
export function useSession() {
  return useQuery({
    queryKey: ["session"],
    staleTime: 60_000,
    retry: false,
    queryFn: async (): Promise<SessionAccount | null> => {
      try {
        return await api.get<SessionAccount>("/v1/auth/me");
      } catch (err) {
        if (isApiError(err) && err.status === 401) {
          return null;
        }
        throw err;
      }
    },
  });
}

import * as React from "react";

import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (body: {
    email: string;
    password: string;
    display_name: string;
    site_password: string;
  }) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = React.createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((error) => {
        // A 401 on load is the normal signed-out case, not a failure.
        if (!(error instanceof ApiError) || error.status !== 401) throw error;
      })
      .finally(() => setLoading(false));
  }, []);

  const value = React.useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn: async (email, password) => setUser(await api.login(email, password)),
      signUp: async (body) => setUser(await api.register(body)),
      signOut: async () => {
        await api.logout();
        setUser(null);
      },
    }),
    [user, loading],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): AuthState {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

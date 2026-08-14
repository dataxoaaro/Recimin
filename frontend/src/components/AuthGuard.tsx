import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "@/lib/auth-context";
import { t } from "@/lib/strings";

/** Gate every app route behind a session. Cosmetic — the API is the real guard. */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <p className="p-4 text-[var(--color-muted)]" role="status">
        {t.loading}
      </p>
    );
  }
  // The search string matters too: a share lands on /import?url=… and must
  // survive the sign-in round-trip intact.
  if (!user) {
    return (
      <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />
    );
  }
  return <>{children}</>;
}

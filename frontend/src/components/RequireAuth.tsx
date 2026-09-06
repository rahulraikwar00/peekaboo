import { Navigate, Outlet, useLocation } from "react-router-dom";

import { AppHeader } from "@/components/AppHeader";
import { useMe } from "@/hooks/use-me";

export function RequireAuth() {
  const location = useLocation();
  const { me, loading, refresh } = useMe();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (!me) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return (
    <div className="min-h-screen">
      <AppHeader authed ownerId={me.owner_id} onLogout={refresh} />
      <Outlet />
    </div>
  );
}
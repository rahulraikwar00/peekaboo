import { Navigate, Outlet } from "react-router-dom";

import { useMe } from "@/hooks/use-me";

export function RequireGuest() {
  const { me, loading } = useMe();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  // Already signed in: skip the login screen.
  if (me) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}
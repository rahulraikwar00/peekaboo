import { Link, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export function AppHeader({
  authed,
  ownerId,
  onLogout,
}: {
  authed: boolean;
  ownerId?: string;
  onLogout?: () => void;
}) {
  const navigate = useNavigate();

  async function handleLogout() {
    await api.logout();
    onLogout?.();
    navigate("/");
  }

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
        <Link
          to={authed ? "/dashboard" : "/"}
          className="text-lg font-semibold tracking-tight"
        >
          Peekaboo
        </Link>
        <nav className="flex items-center gap-2">
          {authed ? (
            <>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/dashboard">Dashboard</Link>
              </Button>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                Log out
              </Button>
            </>
          ) : (
            <Button size="sm" asChild>
              <Link to="/login">Get started</Link>
            </Button>
          )}
        </nav>
      </div>
      <span className="sr-only">{ownerId ? String(ownerId) : ""}</span>
    </header>
  );
}
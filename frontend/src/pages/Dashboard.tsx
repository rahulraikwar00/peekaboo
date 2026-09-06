import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { WelcomeKeyDialog } from "@/components/WelcomeKeyDialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError, relativeTime, type Site } from "@/lib/api";

export function Dashboard() {
  return (
    <>
      <main className="mx-auto w-full max-w-4xl px-4 py-8">
        <SiteManager />
      </main>
      <WelcomeKeyDialog />
    </>
  );
}

function SiteManager() {
  const [sites, setSites] = useState<Site[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [origins, setOrigins] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.sites().then(setSites).catch(() => setSites([]));
  }, []);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const list = origins
        .split(/[\n,]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const { site_id } = await api.createSite(list);
      toast.success("Site created");
      setOrigins("");
      setCreating(false);
      setSites(await api.sites());
      window.history.replaceState(null, "", `/dashboard/sites/${site_id}`);
      window.location.assign(`/dashboard/sites/${site_id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create site");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sites</h1>
          <p className="text-sm text-muted-foreground">
            Add a channel to each site to start receiving messages.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>New site</Button>
      </div>

      <Dialog
        open={creating}
        onOpenChange={(o) => {
          setCreating(o);
          if (o) setOrigins("");
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create a site</DialogTitle>
            <DialogDescription>
              One or more allowed origins, one per line (e.g.
              https://example.com). Visitors on these domains can chat with you.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="origins">Allowed origins</Label>
              <Input
                id="origins"
                placeholder="https://example.com"
                value={origins}
                onChange={(e) => setOrigins(e.target.value)}
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={saving}>
                {saving ? "Creating…" : "Create site"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {sites === null ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Loading…
          </CardContent>
        </Card>
      ) : sites.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No sites yet. Create your first one to get your embed snippet.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {sites.map((site) => (
            <Link key={site.site_id} to={`/dashboard/sites/${site.site_id}`}>
              <Card className="transition-colors hover:border-primary/50 hover:bg-accent/40">
                <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0 p-4">
                  <div className="min-w-0 space-y-1">
                    <CardTitle className="truncate font-mono text-sm">
                      {site.site_id}
                    </CardTitle>
                    <CardDescription className="text-xs">
                      {site.allowed_origins?.join(", ") ||
                        "No allowed origins set"}
                    </CardDescription>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {relativeTime(site.created_at)}
                  </span>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
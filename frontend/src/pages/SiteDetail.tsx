import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ChannelForm } from "@/components/ChannelForm";
import { ChannelList } from "@/components/ChannelList";
import { SiteSnippet } from "@/components/SiteSnippet";
import { StatsCards } from "@/components/StatsCards";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type Integration, type SiteDetail } from "@/lib/api";

export function SiteDetailPage() {
  const { siteId = "" } = useParams();
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .site(siteId)
      .then(setSite)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load site"),
      );
    api
      .integrations(siteId)
      .then(setIntegrations)
      .catch(() => setIntegrations([]));
  }, [siteId]);

  useEffect(() => {
    setSite(null);
    setError(null);
    load();
  }, [load]);

  if (error) {
    return (
      <main className="mx-auto w-full max-w-4xl px-4 py-8">
        <p className="text-sm text-muted-foreground">
          {error}. <Link to="/dashboard" className="underline">Back to sites</Link>
        </p>
      </main>
    );
  }

  if (!site) {
    return (
      <main className="mx-auto w-full max-w-4xl px-4 py-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl space-y-6 px-4 py-8">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate font-mono text-2xl font-semibold tracking-tight">
            {site.site_id}
          </h1>
          <p className="text-sm text-muted-foreground">
            {site.allowed_origins?.join(", ") || "No allowed origins set"}
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link to="/dashboard">All sites</Link>
        </Button>
      </div>

      <StatsCards stats={site.stats} />

      <SiteSnippet siteId={site.site_id} fragment={site.widget_fragment} />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Channels</CardTitle>
        </CardHeader>
        <CardContent>
          <ChannelList
            siteId={site.site_id}
            integrations={integrations}
            onChange={load}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Add a channel</CardTitle>
        </CardHeader>
        <CardContent>
          <ChannelForm siteId={site.site_id} />
        </CardContent>
      </Card>
    </main>
  );
}
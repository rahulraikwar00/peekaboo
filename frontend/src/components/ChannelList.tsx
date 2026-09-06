import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError, maskId, type Integration } from "@/lib/api";

function statusDot(enabled: boolean) {
  return (
    <span
      aria-hidden
      className={`inline-block h-2 w-2 rounded-full ${
        enabled ? "bg-emerald-500" : "bg-muted-foreground/50"
      }`}
    />
  );
}

export function ChannelList({
  siteId,
  integrations,
  onChange,
}: {
  siteId: string;
  integrations: Integration[];
  onChange: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function toggle(integration: Integration) {
    setBusy(integration.integration_id);
    try {
      await api.setIntegrationEnabled(
        siteId,
        integration.integration_id,
        !integration.enabled,
      );
      toast.success(integration.enabled ? "Channel paused" : "Channel resumed");
      onChange();
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Could not update channel",
      );
    } finally {
      setBusy(null);
    }
  }

  async function remove(integration: Integration) {
    if (!window.confirm("Remove this channel? Messages will stop being sent.")) {
      return;
    }
    setBusy(integration.integration_id);
    try {
      await api.removeIntegration(siteId, integration.integration_id);
      toast.success("Channel removed");
      onChange();
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Could not remove channel",
      );
    } finally {
      setBusy(null);
    }
  }

  if (integrations.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No channels yet. Add one above to start receiving visitor messages.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Channel</TableHead>
          <TableHead>Destination</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {integrations.map((integration) => (
          <TableRow key={integration.integration_id}>
            <TableCell className="font-medium capitalize">
              {integration.provider}
            </TableCell>
            <TableCell className="font-mono text-xs">
              {maskId(integration.destination_id)}
            </TableCell>
            <TableCell>
              <span className="inline-flex items-center gap-2 text-sm">
                {statusDot(integration.enabled)}
                {integration.enabled ? "Active" : "Paused"}
              </span>
            </TableCell>
            <TableCell className="text-right">
              <div className="inline-flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy === integration.integration_id}
                  onClick={() => toggle(integration)}
                >
                  {integration.enabled ? "Pause" : "Resume"}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={busy === integration.integration_id}
                  onClick={() => remove(integration)}
                >
                  Remove
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
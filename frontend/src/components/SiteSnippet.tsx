import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SiteSnippet({ siteId, fragment }: { siteId: string; fragment: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(fragment);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Copy failed — select the code manually");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-sm">Embed snippet</CardTitle>
        <Button size="sm" variant="outline" onClick={copy}>
          {copied ? "Copied!" : "Copy"}
        </Button>
      </CardHeader>
      <CardContent>
        <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs leading-relaxed">
          {fragment}
        </pre>
        <p className="mt-2 text-xs text-muted-foreground">
          Paste this right before <code>&lt;/body&gt;</code> on your site (
          {siteId}).
        </p>
      </CardContent>
    </Card>
  );
}
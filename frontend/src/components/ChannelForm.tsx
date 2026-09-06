import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError, type Provider } from "@/lib/api";

const FIELDS: Record<Provider, { name: string; label: string; placeholder: string }[]> = {
  telegram: [
    { name: "token", label: "Bot token", placeholder: "123456:ABC-DEF…" },
    { name: "chat_id", label: "Chat ID", placeholder: "-100123456789" },
  ],
  discord: [
    { name: "token", label: "Bot token", placeholder: "MDEy…" },
    { name: "channel_id", label: "Channel ID", placeholder: "123456789012345678" },
    { name: "public_key", label: "Public key", placeholder: "hex…" },
  ],
  slack: [
    { name: "token", label: "Bot token", placeholder: "xoxb-…" },
    { name: "signing_secret", label: "Signing secret", placeholder: "…" },
    { name: "channel_id", label: "Channel ID", placeholder: "C1234567890" },
  ],
};

export function ChannelForm({ siteId }: { siteId: string }) {
  const [provider, setProvider] = useState<Provider>("telegram");
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function update(name: string, value: string) {
    setValues((v) => ({ ...v, [name]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const result = await api.addIntegration(siteId, { provider, ...values });
      toast.success("Channel added", { description: result.instructions });
      setValues({});
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not add channel");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="provider">Channel</Label>
        <Select
          value={provider}
          onValueChange={(v) => {
            setProvider(v as Provider);
            setValues({});
          }}
        >
          <SelectTrigger id="provider" className="w-full capitalize">
            <SelectValue placeholder="Provider" />
          </SelectTrigger>
          <SelectContent>
            {(["telegram", "discord", "slack"] as Provider[]).map((p) => (
              <SelectItem key={p} value={p} className="capitalize">
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {FIELDS[provider].map((field) => (
        <div key={field.name} className="space-y-1.5">
          <Label htmlFor={field.name}>{field.label}</Label>
          <Input
            id={field.name}
            type="password"
            autoComplete="off"
            placeholder={field.placeholder}
            value={values[field.name] ?? ""}
            onChange={(e) => update(field.name, e.target.value)}
          />
        </div>
      ))}

      <Button type="submit" disabled={saving}>
        {saving ? "Saving…" : "Add channel"}
      </Button>
    </form>
  );
}
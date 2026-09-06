export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export type Me = { owner_id: string };

export type Site = {
  site_id: string;
  allowed_origins?: string[] | null;
  widget_config?: Record<string, unknown> | null;
  created_at?: string | null;
};

export type Stats = {
  messages_received: number;
  replies_sent: number;
  last_message_at?: string | null;
};

export type Integration = {
  integration_id: string;
  provider: string;
  destination_id?: string | null;
  credentials_stored: boolean;
  enabled: boolean;
};

export type SiteDetail = Site & {
  stats: Stats;
  widget_fragment: string;
};

export type Provider = "telegram" | "discord" | "slack";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data && typeof data.error === "string") message = data.error;
    } catch {
      /* keep default */
    }
    throw new ApiError(message, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  me: () => request<Me>("/api/me"),

  logout: () =>
    request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),

  sites: () => request<{ sites: Site[] }>("/api/sites").then((d) => d.sites),

  createSite: (origins: string[]) =>
    request<{ site_id: string }>("/api/sites", {
      method: "POST",
      body: JSON.stringify({ origins }),
    }),

  site: (siteId: string) =>
    request<SiteDetail>(`/api/sites/${siteId}`),

  integrations: (siteId: string) =>
    request<{ integrations: Integration[] }>(
      `/api/sites/${siteId}/integrations`,
    ).then((d) => d.integrations),

  addIntegration: (
    siteId: string,
    payload: Record<string, string>,
  ) =>
    request<Integration & { instructions: string; webhook_url: string }>(
      `/api/sites/${siteId}/integrations`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  setIntegrationEnabled: (
    siteId: string,
    integrationId: string,
    enabled: boolean,
  ) =>
    request<{ integration_id: string; enabled: boolean }>(
      `/api/sites/${siteId}/integrations/${integrationId}/enabled`,
      { method: "POST", body: JSON.stringify({ enabled }) },
    ),

  removeIntegration: (siteId: string, integrationId: string) =>
    request<{ ok: boolean }>(
      `/api/sites/${siteId}/integrations/${integrationId}`,
      { method: "DELETE" },
    ),
};

export const PROVIDER_LABELS: Record<
  string,
  { title: string; hint: string }
> = {
  telegram: {
    title: "Telegram",
    hint: "Bot token and chat ID of the group/channel you want messages in.",
  },
  discord: {
    title: "Discord",
    hint: "Bot token, channel ID, and the bot's public key (from the developer portal).",
  },
  slack: {
    title: "Slack",
    hint: "Bot token, signing secret, and channel ID from your Slack app.",
  },
};

export function maskId(value?: string | null): string {
  if (!value) return "—";
  if (value.length <= 8) return value;
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

export function relativeTime(iso?: string | null): string {
  if (!iso) return "Never";
  const then = new Date(iso.replace(/Z$/, "+00:00")).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  if (diff < 60_000) return "Just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(then).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}
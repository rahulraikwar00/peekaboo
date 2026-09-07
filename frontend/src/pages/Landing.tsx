import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function Landing() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
          <span className="text-lg font-semibold tracking-tight">Peekaboo</span>
          <Button size="sm" asChild>
            <Link to="/dashboard">Get started</Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center gap-6 px-4 py-24 text-center">
        <span className="inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium text-muted-foreground">
          Visitor chat via Telegram, Discord &amp; Slack
        </span>
        <h1 className="max-w-2xl text-4xl font-bold tracking-tight sm:text-6xl">
          Chat with your visitors from your favorite apps
        </h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          Drop one script tag on your site. Visitor messages land in your
          Telegram, Discord, or Slack — answer them right from your phone.
        </p>
        <div className="flex gap-3">
          <Button size="lg" asChild>
            <Link to="/dashboard">Get started free</Link>
          </Button>
        </div>

        <div className="mt-12 grid w-full max-w-2xl grid-cols-1 gap-4 text-left sm:grid-cols-3">
          {[
            {
              title: "One snippet",
              body: "A single <script> tag. No account codes, no SDK.",
            },
            {
              title: "Replies anywhere",
              body: "Answer from Telegram, Discord, or Slack on the go.",
            },
            {
              title: "Privacy first",
              body: "Message bodies are never stored on our servers.",
            },
          ].map((f) => (
            <div key={f.title} className="rounded-lg border p-4">
              <h3 className="mb-1 font-medium">{f.title}</h3>
              <p className="text-sm text-muted-foreground">{f.body}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
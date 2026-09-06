import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.5 12.27c0-.79-.07-1.55-.2-2.28H12v4.31h6.46a5.2 5.2 0 0 1-2.26 3.41v2.84h3.65c2.14-1.97 3.65-4.87 3.65-8.28Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.65-2.84c-1 .67-2.3 1.06-4.29 1.06-3.3 0-6.1-2.23-7.1-5.22H1.1v2.93A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M4.9 14.09a7.2 7.2 0 0 1 0-4.18V6.98H1.1a12 12 0 0 0 0 10.04l3.8-2.93Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.67c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.96 1.19 15.24 0 12 0A12 12 0 0 0 1.1 6.98l3.8 2.93C5.9 6.9 8.7 4.67 12 4.67Z"
      />
    </svg>
  );
}

function GithubIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
      <path d="M12 .5A11.5 11.5 0 0 0 .5 12a11.5 11.5 0 0 0 7.86 10.92c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.36-3.88-1.36-.53-1.33-1.28-1.68-1.28-1.68-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.76.4-1.26.73-1.55-2.55-.3-5.23-1.28-5.23-5.67 0-1.25.45-2.28 1.19-3.08-.12-.3-.52-1.48.11-3.08 0 0 .97-.31 3.18 1.18a11.1 11.1 0 0 1 5.79 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.6.24 2.78.12 3.08.74.8 1.19 1.83 1.19 3.08 0 4.4-2.69 5.37-5.25 5.65.41.36.78 1.06.78 2.14v3.17c0 .3.2.67.8.56A11.5 11.5 0 0 0 23.5 12 11.5 11.5 0 0 0 12 .5Z" />
    </svg>
  );
}

export function Login() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-4xl items-center px-4">
          <span className="text-lg font-semibold tracking-tight">Peekaboo</span>
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center px-4 py-16">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>Sign in</CardTitle>
            <CardDescription>
              Continue with Google or GitHub to manage your sites and channels.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button variant="outline" className="w-full" asChild>
              <a href="/auth/oauth/start?provider=google">
                <GoogleIcon />
                Continue with Google
              </a>
            </Button>
            <Button variant="outline" className="w-full" asChild>
              <a href="/auth/oauth/start?provider=github">
                <GithubIcon />
                Continue with GitHub
              </a>
            </Button>
            <p className="pt-1 text-center text-xs text-muted-foreground">
              You&apos;ll be redirected to authorize Peekaboo.
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
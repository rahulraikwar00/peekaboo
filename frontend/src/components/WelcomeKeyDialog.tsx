import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
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

export function WelcomeKeyDialog() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const apiKey = params.get("key") ?? "";
  const open = params.get("welcome") === "1" && Boolean(apiKey);

  function handleClose() {
    navigate("/dashboard", { replace: true });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Your API key</DialogTitle>
          <DialogDescription>
            This key is shown once. Save it — you&apos;ll need it to sign in on
            other devices or with the CLI.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="api-key-reveal">Account API key</Label>
          <div className="flex gap-2">
            <Input id="api-key-reveal" readOnly value={apiKey} />
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                navigator.clipboard.writeText(apiKey);
              }}
            >
              Copy
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleClose}>I&apos;ve saved it</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
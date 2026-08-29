import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AuthState, AuthType } from "@/hooks/use-studio";

const AUTH_LABELS: Record<AuthType, string> = {
  none: "No auth",
  bearer: "Bearer token",
  apiKey: "API key",
  basic: "Basic auth",
};

export function AuthCard({
  auth,
  onChange,
}: {
  auth: AuthState;
  onChange: (auth: AuthState) => void;
}) {
  const [revealed, setRevealed] = useState(false);

  function patch(next: Partial<AuthState>) {
    onChange({ ...auth, ...next });
  }

  return (
    <Card className="rounded-none border-x-0 border-t-0 shadow-none">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="text-muted-foreground size-4" />
          Authorization
        </CardTitle>
        <CardDescription>Applied to every request you send.</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-col gap-2.5">
        <Select
          value={auth.type}
          onValueChange={(value) => patch({ type: value as AuthType })}
        >
          <SelectTrigger size="sm" className="w-full" aria-label="Authorization type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(AUTH_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {auth.type === "apiKey" ? (
          <div className="flex flex-col gap-1">
            <Label htmlFor="auth-header">Header name</Label>
            <Input
              id="auth-header"
              value={auth.apiKeyHeader}
              onChange={(event) => patch({ apiKeyHeader: event.target.value })}
              placeholder="X-API-Key"
              spellCheck={false}
              className="h-8 font-mono text-[12.5px]"
            />
          </div>
        ) : null}

        {auth.type === "bearer" || auth.type === "apiKey" ? (
          <div className="flex flex-col gap-1">
            <Label htmlFor="auth-token">
              {auth.type === "bearer" ? "Token" : "Key"}
            </Label>
            <div className="flex items-center gap-1.5">
              <Input
                id="auth-token"
                value={auth.token}
                onChange={(event) => patch({ token: event.target.value })}
                type={revealed ? "text" : "password"}
                placeholder="Paste credential"
                autoComplete="off"
                spellCheck={false}
                className="h-8 font-mono text-[12.5px]"
              />
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setRevealed((value) => !value)}
                aria-label={revealed ? "Hide credential" : "Reveal credential"}
                className="text-muted-foreground shrink-0"
              >
                {revealed ? <EyeOff /> : <Eye />}
              </Button>
            </div>
          </div>
        ) : null}

        {auth.type === "basic" ? (
          <div className="flex flex-col gap-1.5">
            <Input
              value={auth.username}
              onChange={(event) => patch({ username: event.target.value })}
              placeholder="Username"
              autoComplete="off"
              className="h-8 text-[12.5px]"
              aria-label="Username"
            />
            <Input
              value={auth.password}
              onChange={(event) => patch({ password: event.target.value })}
              type="password"
              placeholder="Password"
              autoComplete="off"
              className="h-8 text-[12.5px]"
              aria-label="Password"
            />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

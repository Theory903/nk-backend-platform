import { BookOpen, Braces, FileJson, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function TopBar({
  title,
  version,
  openapiUrl,
  theme,
  onToggleTheme,
}: {
  title: string;
  version?: string;
  openapiUrl: string;
  theme: "light" | "dark";
  onToggleTheme: () => void;
}) {
  return (
    <header className="border-border bg-card/60 flex h-13 shrink-0 items-center gap-3 border-b px-4 backdrop-blur">
      <div className="flex min-w-0 items-center gap-2.5">
        <img
          src="/static/branding/logo.png"
          alt=""
          className="size-6 shrink-0 rounded"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-[13px] leading-tight font-semibold">
            {title}
          </span>
          <span className="text-muted-foreground text-[11px] leading-tight">
            API Studio{version ? ` · v${version}` : ""}
          </span>
        </div>
      </div>

      <Separator orientation="vertical" className="mx-1 h-6" />

      <nav className="flex items-center gap-1" aria-label="Documentation views">
        <Button variant="secondary" size="sm" asChild>
          <a href="/api/docs">
            <Braces />
            Studio
          </a>
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <a href="/api/swagger">
            <BookOpen />
            Swagger
          </a>
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <a href="/api/redoc">
            <FileJson />
            ReDoc
          </a>
        </Button>
      </nav>

      <div className="ml-auto flex items-center gap-1.5">
        <Button variant="ghost" size="sm" asChild>
          <a href={openapiUrl} target="_blank" rel="noreferrer">
            openapi.json
          </a>
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="text-muted-foreground"
        >
          {theme === "dark" ? <Sun /> : <Moon />}
        </Button>
      </div>
    </header>
  );
}

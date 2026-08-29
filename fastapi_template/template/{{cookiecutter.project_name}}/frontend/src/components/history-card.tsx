import { History, Trash2 } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { MethodWell } from "@/components/method-badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { HistoryEntry } from "@/hooks/use-studio";
import { relativeTime, statusTone } from "@/lib/format";
import { cn } from "@/lib/utils";

const TONE_TEXT = {
  success: "text-success",
  warning: "text-warning",
  destructive: "text-destructive",
  outline: "text-muted-foreground",
} as const;

export function HistoryCard({
  history,
  onRestore,
  onClear,
}: {
  history: HistoryEntry[];
  onRestore: (entry: HistoryEntry) => void;
  onClear: () => void;
}) {
  return (
    <Card className="flex min-h-0 flex-col rounded-none border-x-0 border-t-0 shadow-none">
      <CardHeader className="flex-row items-center">
        <div className="flex flex-col gap-1">
          <CardTitle className="flex items-center gap-2">
            <History className="text-muted-foreground size-4" />
            History
          </CardTitle>
          <CardDescription>Recent requests from this browser.</CardDescription>
        </div>

        {history.length > 0 ? (
          <CardAction>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onClear}
              aria-label="Clear history"
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2 />
            </Button>
          </CardAction>
        ) : null}
      </CardHeader>

      <CardContent className="min-h-0 overflow-y-auto px-1.5">
        {history.length === 0 ? (
          <EmptyState
            title="No requests yet"
            description="Send one to start a history."
            className="mx-1.5 py-6"
          />
        ) : (
          history.slice(0, 12).map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => onRestore(entry)}
              title={entry.url}
              className="hover:bg-accent/60 group flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors duration-150"
            >
              <MethodWell method={entry.method} />

              <span className="flex min-w-0 flex-col">
                <span className="text-foreground/90 truncate font-mono text-[12.5px] leading-tight">
                  {entry.path}
                </span>
                <span className="text-muted-foreground flex items-center gap-1.5 text-[11px] leading-tight">
                  <span
                    className={cn(
                      "font-medium tabular-nums",
                      TONE_TEXT[statusTone(entry.status)],
                    )}
                  >
                    {entry.status || "ERR"}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span className="tabular-nums">{entry.durationMs} ms</span>
                  <span aria-hidden="true">·</span>
                  <span>{relativeTime(entry.timestamp)}</span>
                </span>
              </span>
            </button>
          ))
        )}
      </CardContent>
    </Card>
  );
}

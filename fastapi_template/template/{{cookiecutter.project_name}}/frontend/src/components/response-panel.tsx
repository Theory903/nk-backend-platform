import { Check, Copy, Inbox } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ResponseState } from "@/hooks/use-studio";
import { formatBytes, formatDuration, statusText, statusTone } from "@/lib/format";

export function ResponsePanel({
  response,
  sending,
}: {
  response: ResponseState | null;
  sending: boolean;
}) {
  const [copied, setCopied] = useState(false);

  async function copyBody() {
    if (!response) return;
    try {
      await navigator.clipboard.writeText(response.body);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* Clipboard unavailable. */
    }
  }

  if (!response) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-6">
        <EmptyState
          icon={Inbox}
          title={sending ? "Waiting for a response…" : "No response yet"}
          description={
            sending
              ? undefined
              : "Send the request to inspect the status, body, and headers."
          }
        />
      </div>
    );
  }

  const tone = statusTone(response.status);

  return (
    <Tabs defaultValue="body" className="min-h-0 flex-1">
      <TabsList>
        <TabsTrigger value="body">Response</TabsTrigger>
        <TabsTrigger value="headers">
          Headers
          <Badge variant="outline" className="px-1 py-0 text-[10px] tabular-nums">
            {response.headers.length}
          </Badge>
        </TabsTrigger>

        <div className="ml-auto flex items-center gap-1.5 self-center">
          <Badge variant={tone} className="tabular-nums">
            {response.status || "ERR"}{" "}
            {response.statusText || statusText(response.status)}
          </Badge>
          <Badge variant="outline" className="tabular-nums">
            {formatDuration(response.durationMs)}
          </Badge>
          {response.sizeBytes !== null ? (
            <Badge variant="outline" className="tabular-nums">
              {formatBytes(response.sizeBytes)}
            </Badge>
          ) : null}
        </div>
      </TabsList>

      <TabsContent value="body" className="relative flex min-h-0 flex-col">
        <Button
          variant="outline"
          size="icon-sm"
          onClick={copyBody}
          aria-label="Copy response body"
          className="absolute top-3 right-4 z-10"
        >
          {copied ? <Check /> : <Copy />}
        </Button>

        <pre className="text-foreground/90 min-h-0 flex-1 overflow-auto p-4 font-mono text-[12.5px] leading-relaxed">
          <code>{response.body || "(empty response body)"}</code>
        </pre>
      </TabsContent>

      <TabsContent value="headers" className="min-h-0 overflow-y-auto p-4">
        {response.headers.length === 0 ? (
          <EmptyState title="No response headers" />
        ) : (
          <table className="w-full border-collapse text-left">
            <tbody>
              {response.headers.map(([name, value]) => (
                <tr key={name} className="border-border/60 border-b last:border-b-0">
                  <th
                    scope="row"
                    className="text-muted-foreground w-1/3 py-1.5 pr-4 align-top font-mono text-[12px] font-medium break-all"
                  >
                    {name}
                  </th>
                  <td className="py-1.5 font-mono text-[12px] break-all">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </TabsContent>
    </Tabs>
  );
}

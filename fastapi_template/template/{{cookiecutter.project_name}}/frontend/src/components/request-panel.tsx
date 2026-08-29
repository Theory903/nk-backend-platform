import { AlertTriangle, Braces, FileText, Sparkles } from "lucide-react";
import { useMemo } from "react";

import { EmptyState } from "@/components/empty-state";
import { KeyValueEditor } from "@/components/kv-editor";
import { MethodTag } from "@/components/method-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { StudioApi } from "@/hooks/use-studio";
import { pathPlaceholders } from "@/lib/openapi";
import { cn } from "@/lib/utils";

export function RequestPanel({ studio }: { studio: StudioApi }) {
  const {
    selected,
    pathValues,
    setPathValues,
    queryRows,
    setQueryRows,
    headerRows,
    setHeaderRows,
    body,
    setBody,
    method,
  } = studio;

  const placeholders = selected ? pathPlaceholders(selected.path) : [];
  const cookieParams = selected?.params.filter((item) => item.in === "cookie") ?? [];
  const sendsBody = !["GET", "HEAD"].includes(method);
  const bodyContentType = selected?.bodyContentType ?? "application/json";

  const bodyError = useMemo(() => {
    if (!body.trim() || !bodyContentType.includes("json")) return null;
    try {
      JSON.parse(body);
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : "Invalid JSON";
    }
  }, [body, bodyContentType]);

  function formatBody() {
    try {
      setBody(JSON.stringify(JSON.parse(body), null, 2));
    } catch {
      /* Leave malformed JSON untouched — the inline error already explains. */
    }
  }

  if (!selected) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-6">
        <EmptyState
          icon={Sparkles}
          title="No endpoint selected"
          description="Pick an operation from the sidebar to build a request, or type a URL above and send it directly."
        />
      </div>
    );
  }

  return (
    <Tabs defaultValue="params" className="min-h-0 flex-1">
      <TabsList>
        <TabsTrigger value="params">
          Params
          {queryRows.length + placeholders.length > 0 ? (
            <Badge variant="outline" className="px-1 py-0 text-[10px] tabular-nums">
              {queryRows.length + placeholders.length}
            </Badge>
          ) : null}
        </TabsTrigger>
        <TabsTrigger value="headers">
          Headers
          {headerRows.length > 0 ? (
            <Badge variant="outline" className="px-1 py-0 text-[10px] tabular-nums">
              {headerRows.length}
            </Badge>
          ) : null}
        </TabsTrigger>
        <TabsTrigger value="body" disabled={!sendsBody}>
          <Braces />
          Body
        </TabsTrigger>
        <TabsTrigger value="docs">
          <FileText />
          Docs
        </TabsTrigger>
      </TabsList>

      <TabsContent value="params" className="overflow-y-auto p-4">
        <div className="flex flex-col gap-5">
          {placeholders.length > 0 ? (
            <section className="flex flex-col gap-2">
              <Label>Path parameters</Label>
              <div className="flex flex-col gap-2">
                {placeholders.map((name) => (
                  <div key={name} className="flex items-center gap-2">
                    <code className="text-muted-foreground w-40 shrink-0 truncate font-mono text-[12.5px]">
                      {name}
                    </code>
                    <Input
                      value={pathValues[name] ?? ""}
                      onChange={(event) =>
                        setPathValues({ ...pathValues, [name]: event.target.value })
                      }
                      placeholder="required"
                      className={cn(
                        "h-8 font-mono text-[12.5px]",
                        !pathValues[name] &&
                          "border-destructive/40 placeholder:text-destructive/70",
                      )}
                      aria-label={`Path parameter ${name}`}
                    />
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <section className="flex flex-col gap-2">
            <Label>Query parameters</Label>
            <KeyValueEditor
              rows={queryRows}
              onChange={setQueryRows}
              addLabel="Add parameter"
              emptyTitle="No query parameters"
              emptyDescription="This operation declares none. You can still add your own."
            />
          </section>
          {cookieParams.length > 0 ? (
            <section className="flex flex-col gap-2">
              <Label>Cookies</Label>
              <p className="text-muted-foreground text-[12px] leading-relaxed">
                The browser session cookies will be included automatically. Use
                your API client if this operation needs custom cookie values.
              </p>
            </section>
          ) : null}
        </div>
      </TabsContent>

      <TabsContent value="headers" className="overflow-y-auto p-4">
        <KeyValueEditor
          rows={headerRows}
          onChange={setHeaderRows}
          addLabel="Add header"
          emptyTitle="No headers"
          emptyDescription="Authorization headers are added automatically from the sidebar."
        />
      </TabsContent>

      <TabsContent value="body" className="flex min-h-0 flex-col p-4">
        <div className="mb-2 flex items-center gap-2">
          <Label>Request body · {bodyContentType}</Label>
          {bodyError ? (
            <Badge variant="destructive" className="gap-1">
              <AlertTriangle />
              Invalid JSON
            </Badge>
          ) : body.trim() ? (
            <Badge variant="success">Valid</Badge>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={formatBody}
            disabled={!body.trim() || Boolean(bodyError)}
          >
            Format
          </Button>
        </div>
        {bodyContentType.startsWith("multipart/") ? (
          <p className="text-muted-foreground mb-2 text-[12px] leading-relaxed">
            Multipart and file uploads are not supported by this text editor.
            Use an API client for this operation.
          </p>
        ) : null}
        {bodyContentType.startsWith("application/x-www-form-urlencoded") ? (
          <p className="text-muted-foreground mb-2 text-[12px] leading-relaxed">
            URL-encoded form submission is not supported by this editor. Use an
            API client for this operation.
          </p>
        ) : null}

        <Textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder={
            selected.bodySchema
              ? "{}"
              : `Enter a ${bodyContentType} request body.`
          }
          spellCheck={false}
          aria-label="Request body"
          className={cn(
            "min-h-0 flex-1 resize-none",
            bodyError && "border-destructive/50",
          )}
        />

        {bodyError ? (
          <p className="text-destructive mt-1.5 font-mono text-[11px]">{bodyError}</p>
        ) : null}
      </TabsContent>

      <TabsContent value="docs" className="overflow-y-auto p-4">
        <article className="flex flex-col gap-4">
          <header className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <MethodTag method={selected.method} />
              <code className="font-mono text-[13px]">{selected.path}</code>
              {selected.deprecated ? (
                <Badge variant="warning">Deprecated</Badge>
              ) : null}
            </div>
            {selected.summary ? (
              <h2 className="text-[15px] font-semibold">{selected.summary}</h2>
            ) : null}
          </header>

          {selected.description ? (
            <p className="text-muted-foreground text-[13px] leading-relaxed whitespace-pre-wrap">
              {selected.description}
            </p>
          ) : (
            <p className="text-muted-foreground text-[13px]">
              No description provided for this operation.
            </p>
          )}

          {selected.params.length > 0 ? (
            <section className="flex flex-col gap-2">
              <Label>Parameters</Label>
              <ul className="flex flex-col gap-1.5">
                {selected.params.map((param) => (
                  <li
                    key={`${param.in}-${param.name}`}
                    className="border-border/60 flex flex-col gap-0.5 border-b pb-1.5 last:border-b-0"
                  >
                    <div className="flex items-center gap-2">
                      <code className="font-mono text-[12.5px]">{param.name}</code>
                      <Badge variant="outline">{param.in}</Badge>
                      {param.required ? (
                        <Badge variant="destructive">required</Badge>
                      ) : null}
                    </div>
                    {param.description ? (
                      <p className="text-muted-foreground text-[12px]">
                        {param.description}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {Object.keys(selected.responses).length > 0 ? (
            <section className="flex flex-col gap-2">
              <Label>Responses</Label>
              <ul className="flex flex-col gap-1">
                {Object.entries(selected.responses).map(([code, detail]) => (
                  <li key={code} className="flex items-center gap-2 text-[12.5px]">
                    <code className="text-muted-foreground w-10 font-mono tabular-nums">
                      {code}
                    </code>
                    <span>{detail?.description ?? ""}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </article>
      </TabsContent>
    </Tabs>
  );
}

import { ChevronDown, ChevronRight, Search, SearchX } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { MethodWell } from "@/components/method-badge";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { type Endpoint, groupByTag } from "@/lib/openapi";
import { cn } from "@/lib/utils";

export function EndpointList({
  endpoints,
  selectedId,
  onSelect,
  searchRef,
}: {
  endpoints: Endpoint[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  searchRef: React.RefObject<HTMLInputElement | null>;
}) {
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();

    return groupByTag(endpoints)
      .map(([tag, items]) => {
        const matched = needle
          ? items.filter((item) =>
              `${item.method} ${item.path} ${item.summary}`
                .toLowerCase()
                .includes(needle),
            )
          : items;
        return [tag, matched] as [string, Endpoint[]];
      })
      .filter(([, items]) => items.length > 0);
  }, [endpoints, query]);

  const total = groups.reduce((sum, [, items]) => sum + items.length, 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative px-3 pb-2">
        <Search className="text-muted-foreground/60 pointer-events-none absolute top-1/2 left-6 size-3.5 -translate-y-1/2" />
        <Input
          ref={searchRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search endpoints…"
          type="search"
          autoComplete="off"
          spellCheck={false}
          aria-label="Search endpoints"
          className="h-8 pl-8 text-[13px]"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {total === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No matching endpoints"
            description={
              query
                ? "Try a different path, verb, or summary keyword."
                : "This schema exposes no operations yet."
            }
            className="mx-1.5"
          />
        ) : (
          groups.map(([tag, items]) => {
            const isCollapsed = collapsed[tag] ?? false;

            return (
              <div key={tag} className="mb-0.5">
                <button
                  type="button"
                  onClick={() =>
                    setCollapsed((prev) => ({ ...prev, [tag]: !isCollapsed }))
                  }
                  className="text-muted-foreground hover:text-foreground hover:bg-accent/60 flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[11px] font-semibold tracking-wide uppercase transition-colors duration-150"
                  aria-expanded={!isCollapsed}
                >
                  {isCollapsed ? (
                    <ChevronRight className="size-3.5 shrink-0" />
                  ) : (
                    <ChevronDown className="size-3.5 shrink-0" />
                  )}
                  <span className="truncate">{tag}</span>
                  <Badge
                    variant="outline"
                    className="ml-auto shrink-0 px-1.5 py-0 text-[10px] tabular-nums"
                  >
                    {items.length}
                  </Badge>
                </button>

                {isCollapsed
                  ? null
                  : items.map((endpoint) => {
                      const active = endpoint.id === selectedId;

                      return (
                        <button
                          key={endpoint.id}
                          type="button"
                          onClick={() => onSelect(endpoint.id)}
                          aria-current={active ? "true" : undefined}
                          title={endpoint.summary || endpoint.path}
                          className={cn(
                            "group flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors duration-150",
                            active
                              ? "bg-accent"
                              : "hover:bg-accent/60",
                          )}
                        >
                          <MethodWell method={endpoint.method} />

                          <span className="flex min-w-0 flex-col">
                            <span
                              className={cn(
                                "truncate font-mono text-[12.5px] leading-tight",
                                active
                                  ? "text-accent-foreground"
                                  : "text-foreground/90",
                                endpoint.deprecated && "line-through opacity-60",
                              )}
                            >
                              {endpoint.path}
                            </span>
                            {endpoint.summary ? (
                              <span className="text-muted-foreground truncate text-[11px] leading-tight">
                                {endpoint.summary}
                              </span>
                            ) : null}
                          </span>

                          <ChevronRight
                            className={cn(
                              "text-muted-foreground/40 ml-auto size-3.5 shrink-0 transition-opacity",
                              active
                                ? "opacity-100"
                                : "opacity-0 group-hover:opacity-100",
                            )}
                          />
                        </button>
                      );
                    })}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

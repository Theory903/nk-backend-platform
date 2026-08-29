import { Plus, X } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type KeyValueRow, newRow } from "@/lib/rows";
import { cn } from "@/lib/utils";

/**
 * Editable key/value table for query parameters and headers.
 *
 * Rows sourced from the OpenAPI schema keep a fixed name and cannot be
 * removed; rows the user adds are fully editable.
 */
export function KeyValueEditor({
  rows,
  onChange,
  addLabel,
  emptyTitle,
  emptyDescription,
}: {
  rows: KeyValueRow[];
  onChange: (rows: KeyValueRow[]) => void;
  addLabel: string;
  emptyTitle: string;
  emptyDescription?: string;
}) {
  function update(id: string, patch: Partial<KeyValueRow>) {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }

  function remove(id: string) {
    onChange(rows.filter((row) => row.id !== id));
  }

  function add() {
    onChange([...rows, newRow()]);
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyDescription} />
      ) : (
        <div className="border-border overflow-hidden rounded-lg border">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-border bg-muted/40 border-b">
                <th className="w-9" />
                <th className="text-muted-foreground px-2 py-1.5 text-left text-[11px] font-medium tracking-wide uppercase">
                  Key
                </th>
                <th className="text-muted-foreground px-2 py-1.5 text-left text-[11px] font-medium tracking-wide uppercase">
                  Value
                </th>
                <th className="w-9" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-border/60 border-b last:border-b-0"
                >
                  <td className="px-2 py-1 text-center align-middle">
                    <input
                      type="checkbox"
                      className="accent-primary size-3.5 cursor-pointer align-middle"
                      checked={row.enabled}
                      onChange={(event) =>
                        update(row.id, { enabled: event.target.checked })
                      }
                      aria-label={`Enable ${row.name || "parameter"}`}
                    />
                  </td>
                  <td className="px-1 py-1 align-middle">
                    <Input
                      value={row.name}
                      readOnly={row.fromSpec}
                      placeholder="name"
                      title={row.description}
                      onChange={(event) =>
                        update(row.id, { name: event.target.value })
                      }
                      className={cn(
                        "h-8 rounded border-transparent bg-transparent font-mono text-[12.5px] shadow-none",
                        row.fromSpec && "text-foreground/90 cursor-default",
                      )}
                    />
                  </td>
                  <td className="px-1 py-1 align-middle">
                    <div className="flex items-center gap-1.5">
                      <Input
                        value={row.value}
                        placeholder={row.required ? "required" : row.typeLabel || "value"}
                        onChange={(event) =>
                          update(row.id, {
                            value: event.target.value,
                            enabled: true,
                          })
                        }
                        className={cn(
                          "h-8 rounded border-transparent bg-transparent font-mono text-[12.5px] shadow-none",
                          row.required &&
                            !row.value &&
                            "placeholder:text-destructive/70",
                        )}
                      />
                      {row.typeLabel ? (
                        <span className="text-muted-foreground/70 shrink-0 font-mono text-[10px]">
                          {row.typeLabel}
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-1 py-1 text-center align-middle">
                    {row.fromSpec ? null : (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="text-muted-foreground hover:text-destructive size-7"
                        onClick={() => remove(row.id)}
                        aria-label={`Remove ${row.name || "row"}`}
                      >
                        <X />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div>
        <Button variant="outline" size="sm" onClick={add}>
          <Plus />
          {addLabel}
        </Button>
      </div>
    </div>
  );
}

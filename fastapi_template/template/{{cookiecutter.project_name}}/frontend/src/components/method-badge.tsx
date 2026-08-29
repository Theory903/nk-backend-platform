import type { HttpMethod } from "@/lib/openapi";
import { cn } from "@/lib/utils";

/**
 * Full class strings per verb — Tailwind scans source statically, so these
 * cannot be assembled from fragments at runtime.
 */
const METHOD_STYLES: Record<HttpMethod, string> = {
  GET: "text-method-get bg-method-get/10 border-method-get/25",
  POST: "text-method-post bg-method-post/10 border-method-post/25",
  PUT: "text-method-put bg-method-put/10 border-method-put/25",
  PATCH: "text-method-patch bg-method-patch/10 border-method-patch/25",
  DELETE: "text-method-delete bg-method-delete/10 border-method-delete/25",
  HEAD: "text-method-head bg-method-head/10 border-method-head/25",
  OPTIONS: "text-method-options bg-method-options/10 border-method-options/25",
};

/** Abbreviations keep the 44px well legible for the longer verbs. */
const SHORT: Partial<Record<HttpMethod, string>> = {
  DELETE: "DEL",
  OPTIONS: "OPT",
  PATCH: "PTCH",
};

export function MethodWell({
  method,
  className,
}: {
  method: HttpMethod;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-lg border font-mono text-[9px] font-semibold tracking-tight tabular-nums",
        METHOD_STYLES[method],
        className,
      )}
      aria-hidden="true"
    >
      {SHORT[method] ?? method}
    </span>
  );
}

export function MethodTag({
  method,
  className,
}: {
  method: HttpMethod;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold",
        METHOD_STYLES[method],
        className,
      )}
    >
      {method}
    </span>
  );
}

export { METHOD_STYLES };

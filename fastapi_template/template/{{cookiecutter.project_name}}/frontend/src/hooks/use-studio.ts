import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { toCurl } from "@/lib/curl";
import { prettyJson } from "@/lib/format";
import {
  type Endpoint,
  type HttpMethod,
  type OpenApiDocument,
  baseUrlFor,
  buildUrl,
  parseEndpoints,
  pathPlaceholders,
  sampleFromSchema,
  schemaTypeLabel,
} from "@/lib/openapi";
import { type KeyValueRow, newRow, rowsToRecord } from "@/lib/rows";

const HISTORY_LIMIT = 40;

export type AuthType = "none" | "bearer" | "apiKey" | "basic";

export interface AuthState {
  type: AuthType;
  token: string;
  /** Header name used when `type` is `apiKey`. */
  apiKeyHeader: string;
  username: string;
  password: string;
}

export interface ResponseState {
  status: number;
  statusText: string;
  durationMs: number;
  sizeBytes: number | null;
  body: string;
  isJson: boolean;
  headers: [string, string][];
}

export interface HistoryEntry {
  id: string;
  method: HttpMethod;
  url: string;
  path: string;
  status: number;
  durationMs: number;
  timestamp: number;
}

const DEFAULT_AUTH: AuthState = {
  type: "none",
  token: "",
  apiKeyHeader: "X-API-Key",
  username: "",
  password: "",
};

export function useStudio(openapiUrl: string) {
  const [doc, setDoc] = useState<OpenApiDocument | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [method, setMethod] = useState<HttpMethod>("GET");
  const [url, setUrl] = useState("");
  const [body, setBody] = useState("");

  const [pathValues, setPathValues] = useState<Record<string, string>>({});
  const [queryRows, setQueryRows] = useState<KeyValueRow[]>([]);
  const [headerRows, setHeaderRows] = useState<KeyValueRow[]>([]);

  const [auth, setAuth] = useState<AuthState>(DEFAULT_AUTH);
  const [response, setResponse] = useState<ResponseState | null>(null);
  const [sending, setSending] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  const endpoints = useMemo(() => (doc ? parseEndpoints(doc) : []), [doc]);
  const selected = useMemo(
    () => endpoints.find((item) => item.id === selectedId) ?? null,
    [endpoints, selectedId],
  );
  const baseUrl = useMemo(() => baseUrlFor(doc), [doc]);

  /** Suppresses URL auto-sync right after the user types in the URL bar. */
  const urlEditedManually = useRef(false);

  // ---------------------------------------------------------------- loading

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setLoadError(null);

      try {
        const res = await fetch(openapiUrl, {
          headers: { Accept: "application/json" },
        });
        if (!res.ok) {
          throw new Error(`${openapiUrl} responded ${res.status}`);
        }
        const json = (await res.json()) as OpenApiDocument;
        if (!cancelled) setDoc(json);
      } catch (error) {
        if (!cancelled) {
          setLoadError(
            error instanceof Error ? error.message : "Unable to load OpenAPI schema",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [openapiUrl]);

  // ------------------------------------------------------------- selection

  const applyEndpoint = useCallback(
    (endpoint: Endpoint, options: { preserveValues?: boolean } = {}) => {
      const currentDoc = doc ?? {};
      const preserved = options.preserveValues ? pathValues : {};

      const nextPathValues: Record<string, string> = {};
      for (const name of pathPlaceholders(endpoint.path)) {
        nextPathValues[name] = preserved[name] ?? "";
      }
      for (const param of endpoint.params.filter((item) => item.in === "path")) {
        nextPathValues[param.name] = preserved[param.name] ?? "";
      }

      const nextQueryRows = endpoint.params
        .filter((param) => param.in === "query")
        .map((param) =>
          newRow({
            name: param.name,
            value: String(param.schema?.default ?? ""),
            enabled: param.required || param.schema?.default !== undefined,
            fromSpec: true,
            required: param.required,
            description: param.description,
            typeLabel: schemaTypeLabel(param.schema, currentDoc),
          }),
        );

      const nextHeaderRows = endpoint.params
        .filter((param) => param.in === "header")
        .map((param) =>
          newRow({
            name: param.name,
            value: "",
            enabled: param.required,
            fromSpec: true,
            required: param.required,
            description: param.description,
            typeLabel: schemaTypeLabel(param.schema, currentDoc),
          }),
        );

      let nextBody = "";
      if (
        endpoint.bodySchema &&
        (endpoint.bodyContentType ?? "application/json").includes("json")
      ) {
        const sample = sampleFromSchema(endpoint.bodySchema, currentDoc);
        if (sample !== null && sample !== undefined) {
          nextBody = JSON.stringify(sample, null, 2);
        }
      }

      setSelectedId(endpoint.id);
      setMethod(endpoint.method);
      setPathValues(nextPathValues);
      setQueryRows(nextQueryRows);
      setHeaderRows(nextHeaderRows);
      setBody(nextBody);
      setResponse(null);
      urlEditedManually.current = false;
      setUrl(buildUrl(baseUrlFor(doc), endpoint.path, nextPathValues, nextQueryRows));
    },
    [doc, pathValues],
  );

  const selectEndpoint = useCallback(
    (id: string) => {
      const endpoint = endpoints.find((item) => item.id === id);
      if (endpoint) applyEndpoint(endpoint);
    },
    [applyEndpoint, endpoints],
  );

  // Keep the URL bar in sync with path/query edits unless it was hand-edited.
  useEffect(() => {
    if (!selected || urlEditedManually.current) return;
    setUrl(buildUrl(baseUrl, selected.path, pathValues, queryRows));
  }, [baseUrl, selected, pathValues, queryRows]);

  // ---------------------------------------------------------------- request

  const effectiveHeaders = useCallback((): Record<string, string> => {
    const headers = rowsToRecord(headerRows);
    const hasHeader = (name: string) =>
      Object.keys(headers).some((key) => key.toLowerCase() === name.toLowerCase());
    const canSendAuth = (() => {
      try {
        return new URL(url, window.location.origin).origin === window.location.origin;
      } catch {
        return false;
      }
    })();

    if (canSendAuth && auth.type === "bearer" && auth.token && !hasHeader("Authorization")) {
      headers.Authorization = `Bearer ${auth.token}`;
    }
    if (canSendAuth && auth.type === "apiKey" && auth.token && !hasHeader(auth.apiKeyHeader || "X-API-Key")) {
      headers[auth.apiKeyHeader || "X-API-Key"] = auth.token;
    }
    if (
      canSendAuth &&
      auth.type === "basic" &&
      (auth.username || auth.password) &&
      !hasHeader("Authorization")
    ) {
      headers.Authorization = `Basic ${btoa(`${auth.username}:${auth.password}`)}`;
    }

    const sendsBody = !["GET", "HEAD"].includes(method);
    if (sendsBody && body.trim() && !hasHeader("Content-Type")) {
      headers["Content-Type"] = selected?.bodyContentType ?? "application/json";
    }

    return headers;
  }, [auth, body, headerRows, method, selected, url]);

  /** Required request values that are still empty. */
  const missingRequired = useMemo(() => {
    if (!selected) return [];
    const unsupportedBody =
      selected.bodyContentType?.startsWith("multipart/") ||
      selected.bodyContentType?.startsWith("application/x-www-form-urlencoded");
    if (urlEditedManually.current) return unsupportedBody ? ["request body"] : [];

    const missing: string[] = [];
    for (const name of pathPlaceholders(selected.path)) {
      if (!pathValues[name]) missing.push(name);
    }
    for (const row of queryRows) {
      if (row.required && (!row.enabled || !row.value)) missing.push(row.name);
    }
    for (const row of headerRows) {
      if (row.required && (!row.enabled || !row.value)) missing.push(row.name);
    }
    if (selected.bodyRequired && !body.trim()) missing.push("request body");
    if (selected.bodyContentType?.startsWith("multipart/")) {
      missing.push("multipart body");
    }
    if (selected.bodyContentType?.startsWith("application/x-www-form-urlencoded")) {
      missing.push("url-encoded body");
    }
    return missing;
  }, [body, headerRows, pathValues, queryRows, selected, url]);

  const send = useCallback(async () => {
    if (sending || !url || missingRequired.length > 0) return;

    setSending(true);
    const started = performance.now();

    try {
      const target = new URL(url, window.location.origin);
      if (target.origin !== window.location.origin) {
        throw new Error("Cross-origin requests are blocked by the documentation console.");
      }

      const sendsBody = !["GET", "HEAD"].includes(method);
      const res = await fetch(url, {
        method,
        headers: effectiveHeaders(),
        body: sendsBody && body.trim() ? body : undefined,
        // Keep ambient session cookies on same-origin API calls only.
        credentials: "same-origin",
      });

      const raw = await res.text();
      const { text, isJson } = prettyJson(raw);
      const durationMs = Math.round(performance.now() - started);

      setResponse({
        status: res.status,
        statusText: res.statusText,
        durationMs,
        sizeBytes: new Blob([raw]).size,
        body: text,
        isJson,
        headers: [...res.headers.entries()],
      });

      const entry: HistoryEntry = {
        id: `${Date.now()}-${method}-${url}`,
        method,
        url,
        path: (() => {
          try {
            return new URL(url, window.location.origin).pathname;
          } catch {
            return url;
          }
        })(),
        status: res.status,
        durationMs,
        timestamp: Date.now(),
      };

      setHistory((previous) => {
        const deduped = previous.filter(
          (item) => !(item.method === entry.method && item.url === entry.url),
        );
        return [entry, ...deduped].slice(0, HISTORY_LIMIT);
      });
    } catch (error) {
      setResponse({
        status: 0,
        statusText: "Network error",
        durationMs: Math.round(performance.now() - started),
        sizeBytes: null,
        body: JSON.stringify(
          {
            error: "Request failed",
            message: error instanceof Error ? error.message : String(error),
            hint: "Check that the server is running and that CORS allows this origin.",
          },
          null,
          2,
        ),
        isJson: true,
        headers: [],
      });
    } finally {
      setSending(false);
    }
  }, [body, effectiveHeaders, method, missingRequired, sending, url]);

  const curlCommand = useCallback(
    () => toCurl({ method, url, headers: effectiveHeaders(), body }),
    [body, effectiveHeaders, method, url],
  );

  const restoreHistory = useCallback(
    (entry: HistoryEntry) => {
      setMethod(entry.method);
      setUrl(entry.url);
      urlEditedManually.current = true;

      const match = endpoints.find(
        (item) => item.method === entry.method && entry.path.endsWith(item.path),
      );
      if (match) setSelectedId(match.id);
    },
    [endpoints],
  );

  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  const updateUrl = useCallback((next: string) => {
    urlEditedManually.current = true;
    setUrl(next);
  }, []);

  const resetUrlToSpec = useCallback(() => {
    if (!selected) return;
    urlEditedManually.current = false;
    setUrl(buildUrl(baseUrl, selected.path, pathValues, queryRows));
  }, [baseUrl, pathValues, queryRows, selected]);

  return {
    doc,
    loading,
    loadError,
    endpoints,
    selected,
    selectedId,
    selectEndpoint,

    method,
    setMethod,
    url,
    updateUrl,
    resetUrlToSpec,
    urlIsCustom: urlEditedManually.current,

    body,
    setBody,
    pathValues,
    setPathValues,
    queryRows,
    setQueryRows,
    headerRows,
    setHeaderRows,

    auth,
    setAuth,

    response,
    sending,
    send,
    missingRequired,
    curlCommand,

    history,
    restoreHistory,
    clearHistory,
  };
}

export type StudioApi = ReturnType<typeof useStudio>;

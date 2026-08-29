/** Minimal OpenAPI 3.x reader — only the parts the Studio needs. */

import type { KeyValueRow } from "@/lib/rows";

export const HTTP_METHODS = [
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
  "HEAD",
  "OPTIONS",
] as const;

export type HttpMethod = (typeof HTTP_METHODS)[number];

export type ParamLocation = "query" | "path" | "header" | "cookie";

export interface JsonSchema {
  type?: string;
  format?: string;
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  required?: string[];
  enum?: unknown[];
  default?: unknown;
  example?: unknown;
  examples?: unknown[];
  title?: string;
  description?: string;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  allOf?: JsonSchema[];
  $ref?: string;
  additionalProperties?: JsonSchema | boolean;
  nullable?: boolean;
}

export interface ParamSpec {
  name: string;
  in: ParamLocation;
  required: boolean;
  description?: string;
  schema?: JsonSchema;
}

export interface Endpoint {
  /** Stable identity used for selection and persistence: `METHOD path`. */
  id: string;
  method: HttpMethod;
  path: string;
  summary: string;
  description: string;
  tags: string[];
  deprecated: boolean;
  params: ParamSpec[];
  bodySchema: JsonSchema | null;
  bodyContentType: string | null;
  bodyRequired: boolean;
  responses: Record<string, { description?: string }>;
}

export interface OpenApiDocument {
  openapi?: string;
  info?: { title?: string; version?: string; description?: string };
  servers?: { url: string; description?: string }[];
  paths?: Record<string, Record<string, unknown>>;
  components?: { schemas?: Record<string, JsonSchema> };
}

/**
 * Resolve `$ref` pointers against the document.
 *
 * FastAPI emits request bodies as `$ref: '#/components/schemas/Model'`, so
 * without this the body schema has no `properties` and no sample can be built.
 * `seen` guards against self-referential models, which are legal and common.
 */
export function resolveRef(
  schema: JsonSchema | undefined,
  doc: OpenApiDocument,
  seen: Set<string> = new Set(),
): JsonSchema | undefined {
  if (!schema) return undefined;
  if (!schema.$ref) return schema;

  const ref = schema.$ref;
  if (seen.has(ref)) return {};
  seen.add(ref);

  if (!ref.startsWith("#/")) return {};

  let node: unknown = doc;
  for (const rawSegment of ref.slice(2).split("/")) {
    const segment = rawSegment.replaceAll("~1", "/").replaceAll("~0", "~");
    if (node === null || typeof node !== "object") return {};
    node = (node as Record<string, unknown>)[segment];
  }

  return resolveRef(node as JsonSchema | undefined, doc, seen);
}

/** Collapse `anyOf`/`oneOf`/`allOf` down to something renderable. */
function flatten(
  schema: JsonSchema | undefined,
  doc: OpenApiDocument,
): JsonSchema | undefined {
  const resolved = resolveRef(schema, doc);
  if (!resolved) return undefined;

  if (resolved.allOf?.length) {
    const merged: JsonSchema = { type: "object", properties: {}, required: [] };
    for (const part of resolved.allOf) {
      const flat = flatten(part, doc);
      Object.assign(merged.properties!, flat?.properties ?? {});
      merged.required!.push(...(flat?.required ?? []));
    }
    return merged;
  }

  const union = resolved.anyOf ?? resolved.oneOf;
  if (union?.length) {
    // Prefer the first non-null branch — `Optional[X]` becomes `anyOf[X, null]`.
    const branch = union.find((item) => resolveRef(item, doc)?.type !== "null");
    return flatten(branch ?? union[0], doc);
  }

  return resolved;
}

/** Build a representative JSON value so the body editor starts from a shape. */
export function sampleFromSchema(
  schema: JsonSchema | undefined,
  doc: OpenApiDocument,
  depth = 0,
): unknown {
  const flat = flatten(schema, doc);
  if (!flat || depth > 6) return null;

  if (flat.example !== undefined) return flat.example;
  if (flat.default !== undefined) return flat.default;
  if (flat.enum?.length) return flat.enum[0];

  switch (flat.type) {
    case "object":
      break;
    case "array":
      return [sampleFromSchema(flat.items, doc, depth + 1)];
    case "integer":
      return 0;
    case "number":
      return 0;
    case "boolean":
      return false;
    case "null":
      return null;
    case "string":
      if (flat.format === "date-time") return new Date().toISOString();
      if (flat.format === "date") return new Date().toISOString().slice(0, 10);
      if (flat.format === "uuid") return "00000000-0000-0000-0000-000000000000";
      if (flat.format === "email") return "user@example.com";
      return "";
    default:
      if (!flat.properties) return null;
  }

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(flat.properties ?? {})) {
    result[key] = sampleFromSchema(value, doc, depth + 1);
  }
  return result;
}

/** Human-readable type label for parameter hints, e.g. `string`, `integer[]`. */
export function schemaTypeLabel(
  schema: JsonSchema | undefined,
  doc: OpenApiDocument,
): string {
  const flat = flatten(schema, doc);
  if (!flat) return "";
  if (flat.type === "array") {
    return `${schemaTypeLabel(flat.items, doc) || "any"}[]`;
  }
  return flat.type ?? "";
}

function isHttpMethod(value: string): value is Lowercase<HttpMethod> {
  return HTTP_METHODS.includes(value.toUpperCase() as HttpMethod);
}

export function parseEndpoints(doc: OpenApiDocument): Endpoint[] {
  const endpoints: Endpoint[] = [];

  for (const [path, pathItem] of Object.entries(doc.paths ?? {})) {
    if (!pathItem || typeof pathItem !== "object") continue;

    // Parameters declared on the path apply to every operation beneath it.
    const shared = (pathItem.parameters ?? []) as ParamSpec[];

    for (const [rawMethod, rawOperation] of Object.entries(pathItem)) {
      if (!isHttpMethod(rawMethod)) continue;
      if (!rawOperation || typeof rawOperation !== "object") continue;

      const operation = rawOperation as Record<string, unknown>;
      const method = rawMethod.toUpperCase() as HttpMethod;

      const parameterByKey = new Map<string, ParamSpec>();
      for (const param of [
        ...shared,
        ...((operation.parameters ?? []) as ParamSpec[]),
      ]) {
        const resolvedParam = resolveRef(
          param as unknown as JsonSchema,
          doc,
        ) as unknown as ParamSpec;
        if (resolvedParam?.name && resolvedParam.in) {
          parameterByKey.set(
            `${resolvedParam.in}:${resolvedParam.name}`,
            resolvedParam,
          );
        }
      }

      const params = [...parameterByKey.values()];

      const requestBody = resolveRef(
        operation.requestBody as JsonSchema | undefined,
        doc,
      ) as
        | { required?: boolean; content?: Record<string, { schema?: JsonSchema }> }
        | undefined;

      const jsonContent =
        requestBody?.content?.["application/json"] ??
        Object.values(requestBody?.content ?? {})[0];
      const bodyContentTypes = Object.keys(requestBody?.content ?? {});
      const bodyContentType =
        bodyContentTypes.includes("application/json")
          ? "application/json"
          : bodyContentTypes[0] ?? null;

      const description = String(operation.description ?? "");
      const summary =
        String(operation.summary ?? "") || description.split("\n")[0] || "";

      endpoints.push({
        id: `${method} ${path}`,
        method,
        path,
        summary,
        description,
        tags: ((operation.tags as string[]) ?? []).filter(Boolean),
        deprecated: Boolean(operation.deprecated),
        params,
        bodySchema: jsonContent?.schema ?? null,
        bodyContentType,
        bodyRequired: Boolean(requestBody?.required),
        responses:
          (operation.responses as Record<string, { description?: string }>) ?? {},
      });
    }
  }

  return endpoints;
}

export function groupByTag(endpoints: Endpoint[]): [string, Endpoint[]][] {
  const groups = new Map<string, Endpoint[]>();

  for (const endpoint of endpoints) {
    for (const tag of endpoint.tags.length ? endpoint.tags : ["Default"]) {
      const bucket = groups.get(tag) ?? [];
      bucket.push(endpoint);
      groups.set(tag, bucket);
    }
  }

  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export function baseUrlFor(doc: OpenApiDocument | null): string {
  const server = doc?.servers?.[0]?.url;
  if (!server || server === "/") return window.location.origin;
  if (/^https?:\/\//.test(server)) return server.replace(/\/$/, "");
  return `${window.location.origin}/${server.replace(/^\//, "")}`.replace(/\/$/, "");
}

/**
 * Interpolate `{path}` placeholders and append enabled query rows.
 *
 * Unfilled path placeholders are left literal (`/items/{item_id}`) so the URL
 * bar visibly shows what still needs a value instead of silently breaking.
 */
export function buildUrl(
  baseUrl: string,
  path: string,
  pathValues: Record<string, string>,
  queryRows: KeyValueRow[],
): string {
  let rendered = path;

  for (const [name, value] of Object.entries(pathValues)) {
    if (!value) continue;
    rendered = rendered.replaceAll(`{${name}}`, encodeURIComponent(value));
  }

  const query = new URLSearchParams();
  for (const row of queryRows) {
    if (!row.enabled || !row.name.trim() || row.value === "") continue;
    query.append(row.name.trim(), row.value);
  }

  const search = query.toString();
  return `${baseUrl.replace(/\/$/, "")}/${rendered.replace(/^\//, "")}${
    search ? `?${search}` : ""
  }`;
}

/** Path placeholders present in a path template, e.g. `["item_id"]`. */
export function pathPlaceholders(path: string): string[] {
  return [...path.matchAll(/\{([^}]+)\}/g)].map((match) => match[1]);
}

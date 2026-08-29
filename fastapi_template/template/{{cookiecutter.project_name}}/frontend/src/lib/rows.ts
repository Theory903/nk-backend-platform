/** An editable key/value row used by the params and headers tables. */
export interface KeyValueRow {
  id: string;
  name: string;
  value: string;
  enabled: boolean;
  /** Declared by the OpenAPI schema — the name is fixed and cannot be removed. */
  fromSpec?: boolean;
  required?: boolean;
  description?: string;
  typeLabel?: string;
}

let counter = 0;

export function newRow(partial: Partial<KeyValueRow> = {}): KeyValueRow {
  counter += 1;
  return {
    id: `row-${counter}`,
    name: "",
    value: "",
    enabled: true,
    ...partial,
  };
}

/** Collapse rows into a plain object, dropping disabled and unnamed entries. */
export function rowsToRecord(rows: KeyValueRow[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const row of rows) {
    if (!row.enabled || !row.name.trim()) continue;
    result[row.name.trim()] = row.value;
  }
  return result;
}

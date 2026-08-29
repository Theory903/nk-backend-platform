/** Single-quote a value for POSIX shells by closing/reopening around quotes. */
function shellQuote(value: string): string {
  return `'${value.replaceAll("'", `'\\''`)}'`;
}

export interface CurlInput {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string;
}

export function toCurl({ method, url, headers, body }: CurlInput): string {
  const parts = [`curl -X ${method}`, shellQuote(url)];

  for (const [name, value] of Object.entries(headers)) {
    if (!name || !value) continue;
    parts.push(`-H ${shellQuote(`${name}: ${value}`)}`);
  }

  const sendsBody = !["GET", "HEAD"].includes(method);
  if (sendsBody && body.trim()) {
    parts.push(`--data-raw ${shellQuote(body)}`);
  }

  // Multi-line with continuations so it pastes cleanly into a terminal.
  return parts.join(" \\\n  ");
}

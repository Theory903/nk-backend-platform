import { Check, Copy, RotateCcw, Send } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { HTTP_METHODS, type HttpMethod } from "@/lib/openapi";
import { METHOD_STYLES } from "@/components/method-badge";
import { cn } from "@/lib/utils";

export function RequestBar({
  method,
  onMethodChange,
  url,
  onUrlChange,
  onResetUrl,
  urlIsCustom,
  sending,
  disabled,
  onSend,
  curlCommand,
}: {
  method: HttpMethod;
  onMethodChange: (method: HttpMethod) => void;
  url: string;
  onUrlChange: (url: string) => void;
  onResetUrl: () => void;
  urlIsCustom: boolean;
  sending: boolean;
  disabled: boolean;
  onSend: () => void;
  curlCommand: () => string;
}) {
  const [copied, setCopied] = useState(false);

  async function copyCurl() {
    try {
      await navigator.clipboard.writeText(curlCommand());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* Clipboard blocked (insecure origin or denied permission). */
    }
  }

  return (
    <div className="border-border flex shrink-0 items-center gap-2 border-b px-4 py-3">
      <Select
        value={method}
        onValueChange={(value) => onMethodChange(value as HttpMethod)}
      >
        <SelectTrigger
          className={cn("w-[108px] font-mono text-[12.5px] font-semibold", METHOD_STYLES[method])}
          aria-label="HTTP method"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {HTTP_METHODS.map((item) => (
            <SelectItem key={item} value={item} className="font-mono text-[12.5px]">
              {item}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="relative flex-1">
        <Input
          value={url}
          onChange={(event) => onUrlChange(event.target.value)}
          placeholder="https://…"
          spellCheck={false}
          autoComplete="off"
          aria-label="Request URL"
          className="pr-9 font-mono text-[12.5px]"
        />
        {urlIsCustom ? (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onResetUrl}
            title="Reset URL to the schema definition"
            aria-label="Reset URL to the schema definition"
            className="text-muted-foreground absolute top-1/2 right-1 size-7 -translate-y-1/2"
          >
            <RotateCcw />
          </Button>
        ) : null}
      </div>

      <Button variant="outline" size="sm" onClick={copyCurl} disabled={!url}>
        {copied ? <Check /> : <Copy />}
        {copied ? "Copied" : "cURL"}
      </Button>

      <Button size="lg" onClick={onSend} disabled={disabled || sending || !url}>
        <Send />
        {sending ? "Sending…" : "Send"}
      </Button>
    </div>
  );
}

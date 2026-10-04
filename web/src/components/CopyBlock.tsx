import { useId, useState } from "react";
import { Button } from "./Button";

interface CopyBlockProps {
  /** What the text is, above it: "Your first question", "Claude Desktop's configuration". */
  label: string;
  /** The text to copy, shown exactly, line breaks kept. */
  text: string;
}

/**
 * Text the person copies somewhere else — a prompt, a command, a configuration — on `sunken`, with
 * a "Copy" button that says "Copied" once it has. The text wraps rather than scrolling sideways,
 * and stays selectable for a browser that refuses the clipboard.
 */
export function CopyBlock({ label, text }: CopyBlockProps) {
  const labelId = useId();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <figure aria-labelledby={labelId} className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <figcaption id={labelId} className="text-label text-ink">
          {label}
        </figcaption>
        <Button variant="link" aria-describedby={labelId} onClick={() => void copy()}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="rounded-md border border-rule bg-sunken p-4 font-sans text-body break-words whitespace-pre-wrap text-ink">
        {text}
      </pre>
    </figure>
  );
}

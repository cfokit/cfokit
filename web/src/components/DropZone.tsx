import { useId, useRef, useState, type DragEvent } from "react";
import { Button } from "./Button";
import { FileIcon } from "./icons";

interface DropZoneProps {
  /** One sentence: "Drop the QuickBooks export here, or choose it from your computer." */
  prompt: string;
  /** The file types the picker offers, as `<input accept>` takes them: ".zip". */
  accept?: string;
  /** Called with the file chosen or dropped. */
  onFile: (file: File) => void;
}

/**
 * Where a file is chosen. The "Choose file" button opens the device's picker, and is the whole
 * of it on a touch device, where there is nothing to drop. With a pointer, dropping a file is a
 * shortcut beside the button, and the border turns `accent` while a file is over the zone.
 */
export function DropZone({ prompt, accept, onFile }: DropZoneProps) {
  const input = useRef<HTMLInputElement>(null);
  const promptId = useId();
  const [over, setOver] = useState(false);

  const onDragOver = (event: DragEvent) => {
    event.preventDefault();
    setOver(true);
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file !== undefined) onFile(file);
  };

  return (
    <div
      onDragOver={onDragOver}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={[
        "flex flex-col items-center gap-4 rounded-md border border-dashed bg-sunken px-6 py-10 text-center",
        "pointer-coarse:border-0 pointer-coarse:bg-transparent pointer-coarse:p-0",
        over ? "border-accent" : "border-control-border",
      ].join(" ")}
    >
      <FileIcon size={24} className="text-ink-muted pointer-coarse:hidden" />
      <p id={promptId} className="max-w-reading-max text-body text-ink pointer-coarse:hidden">
        {prompt}
      </p>
      <Button aria-describedby={promptId} onClick={() => input.current?.click()}>
        Choose file
      </Button>
      <input
        ref={input}
        type="file"
        accept={accept}
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file !== undefined) onFile(file);
          event.target.value = "";
        }}
      />
    </div>
  );
}

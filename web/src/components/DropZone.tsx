import { useId, useRef, useState, type DragEvent } from "react";
import { Button } from "./Button";
import { FileIcon } from "./icons";

interface DropZoneProps {
  /** One sentence: "Drop the QuickBooks export here, or choose it from your computer." */
  prompt: string;
  /** The file types the picker offers, as `<input accept>` takes them: ".zip". */
  accept?: string;
  /** Called with the file chosen or dropped, when it is of a type `accept` allows. */
  onFile: (file: File) => void;
  /**
   * Called instead of `onFile` with a file `accept` does not allow. Only the picker filters by
   * `accept`, and only as a hint: a dropped file, or one chosen with "All files", is anything.
   */
  onReject: (file: File) => void;
}

/** Whether `file` is one of the types an `<input accept>` list names: ".zip", "application/zip", "image/*". */
export function accepts(accept: string | undefined, file: File): boolean {
  if (accept === undefined || accept.trim() === "") return true;
  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();
  return accept
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .some((entry) => {
      if (entry.startsWith(".")) return name.endsWith(entry);
      if (entry.endsWith("/*")) return type.startsWith(entry.slice(0, -1));
      return entry !== "" && type === entry;
    });
}

/**
 * Where a file is chosen. The "Choose file" button opens the device's picker, and is the whole
 * of it on a touch device, where there is nothing to drop. With a pointer, dropping a file is a
 * shortcut beside the button, and the border turns `accent` while a file is over the zone.
 */
export function DropZone({ prompt, accept, onFile, onReject }: DropZoneProps) {
  const input = useRef<HTMLInputElement>(null);
  const promptId = useId();
  const [over, setOver] = useState(false);
  const take = (file: File) => (accepts(accept, file) ? onFile(file) : onReject(file));

  const onDragOver = (event: DragEvent) => {
    event.preventDefault();
    setOver(true);
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file !== undefined) take(file);
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
          if (file !== undefined) take(file);
          event.target.value = "";
        }}
      />
    </div>
  );
}

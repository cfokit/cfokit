import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useExternalStoreRuntime,
  type AssistantRuntime,
  type ThreadMessageLike,
  type ToolCallMessagePartProps,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";

interface ConversationProps {
  /** The live conversation, from an assistant-ui runtime such as the AG-UI one. */
  runtime?: AssistantRuntime;
  /**
   * A conversation to show without one: read-only, as in the gallery and the design system's
   * previews. Ignored when `runtime` is given.
   */
  messages?: readonly ThreadMessageLike[];
  /** What the composer asks for, which is also its accessible name: "Ask about the books". */
  placeholder: string;
}

const REMARK = [remarkGfm];

/** The model's text, as Markdown rendered to elements and never as HTML (ADR-0049 § 6). */
function Text() {
  return (
    <MarkdownTextPrimitive
      remarkPlugins={REMARK}
      className={[
        "flex max-w-reading-max flex-col gap-3 text-body text-ink",
        "[&_ol]:list-decimal [&_ol]:pl-6 [&_ul]:list-disc [&_ul]:pl-6",
        "[&_strong]:font-semibold [&_a]:text-accent [&_a]:underline",
        "[&_table]:border-collapse [&_td]:border-b [&_td]:border-rule [&_td]:py-1 [&_td]:pr-4",
        "[&_th]:border-b [&_th]:border-control-border [&_th]:py-1 [&_th]:pr-4 [&_th]:text-left",
        "[&_code]:rounded-sm [&_code]:bg-sunken [&_code]:px-1",
      ].join(" ")}
    />
  );
}

/** A tool the agent called, in a line: what it looked at, not what it was sent. */
function ToolLine({ toolName, status }: ToolCallMessagePartProps) {
  const what = toolName.replaceAll("_", " ");
  return (
    <p className="text-caption text-ink-muted">
      {status.type === "running" ? `Reading ${what}…` : `Read ${what}`}
    </p>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-end">
      <div className="max-w-reading-max rounded-md bg-sunken px-4 py-3 text-body text-ink">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="flex flex-col gap-2">
      <MessagePrimitive.Parts components={{ Text, tools: { Fallback: ToolLine } }} />
    </MessagePrimitive.Root>
  );
}

const MESSAGES = { UserMessage, AssistantMessage };

function Thread({ placeholder, readOnly }: { placeholder: string; readOnly: boolean }) {
  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col gap-4">
      <ThreadPrimitive.Viewport
        className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto"
        aria-live="polite"
      >
        <ThreadPrimitive.Messages components={MESSAGES} />
      </ThreadPrimitive.Viewport>
      {!readOnly && (
        <ComposerPrimitive.Root className="flex items-end gap-2 rounded-md border border-control-border bg-surface p-2">
          <ComposerPrimitive.Input
            aria-label={placeholder}
            placeholder={placeholder}
            rows={1}
            className="min-h-target-min flex-1 resize-none bg-transparent px-2 py-2 text-input text-ink outline-none placeholder:text-ink-muted"
          />
          <ThreadPrimitive.If running={false}>
            <ComposerPrimitive.Send className="inline-flex min-h-target-min cursor-pointer items-center rounded-md border border-accent bg-accent px-6 text-body font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60">
              Send
            </ComposerPrimitive.Send>
          </ThreadPrimitive.If>
          <ThreadPrimitive.If running>
            <ComposerPrimitive.Cancel className="inline-flex min-h-target-min cursor-pointer items-center rounded-md border border-control-border bg-surface px-6 text-body font-semibold text-ink hover:bg-sunken">
              Stop
            </ComposerPrimitive.Cancel>
          </ThreadPrimitive.If>
        </ComposerPrimitive.Root>
      )}
    </ThreadPrimitive.Root>
  );
}

const NONE: readonly ThreadMessageLike[] = [];

/**
 * A conversation with CFOKit's agent: the person's messages on the right in a sunken panel, the
 * agent's answers on the left as text, each tool it used as one muted line, and a composer below
 * with Send, or Stop while the agent answers. Built on assistant-ui's primitives (ADR-0075 § 3)
 * and styled from the design system like every other component.
 */
export function Conversation({ runtime, messages = NONE, placeholder }: ConversationProps) {
  const shown = useExternalStoreRuntime<ThreadMessageLike>({
    messages,
    convertMessage: (message) => message,
    onNew: async () => {},
  });
  return (
    <AssistantRuntimeProvider runtime={runtime ?? shown}>
      <Thread placeholder={placeholder} readOnly={runtime === undefined} />
    </AssistantRuntimeProvider>
  );
}

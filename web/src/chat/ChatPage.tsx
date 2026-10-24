import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { HttpAgent } from "@ag-ui/client";
import { fromThreadMessageLike, type ThreadMessage } from "@assistant-ui/react";
import { fromAgUiMessages, useAgUiRuntime, type AgUiMessage } from "@assistant-ui/react-ag-ui";
import { useAuth } from "react-oidc-context";
import { ApiError, useApi } from "../api";
import { Button, Conversation, Notice, TextLink } from "../components";
import { useCompanyName } from "../questions/QuestionsPage";
import { PersonFrame } from "../settings/PersonFrame";
import { useStarted } from "../start/state";
import { useAgentUrl } from "./agentUrl";

/** CFOKit's agent as the API records it acting for a person (ADR-0077), for the allow page. */
export const AGENT = "client:cfokit-agent";

/** The agent's history as assistant-ui's repository: each message after the one before it. */
export function thread(
  messages: AgUiMessage[],
): { message: ThreadMessage; parentId: string | null }[] {
  let parentId: string | null = null;
  return fromAgUiMessages(messages).map((like, index) => {
    const message = fromThreadMessageLike(like, `history-${index}`, {
      type: "complete",
      reason: "unknown",
    });
    const entry = { message, parentId };
    parentId = message.id;
    return entry;
  });
}

/** Why a turn or the history was refused, from the refusal's stable `code` (ADR-0015). */
export function refusalOf(error: unknown): { code: string; message: string } {
  const payload = (error as { payload?: { code?: unknown; message?: unknown } }).payload;
  if (payload && typeof payload.code === "string") {
    return {
      code: payload.code,
      message: typeof payload.message === "string" ? payload.message : "",
    };
  }
  return { code: "unexpected", message: error instanceof Error ? error.message : String(error) };
}

function Refusal({ code, message }: { code: string; message: string }) {
  const navigate = useNavigate();
  if (code === "agent_not_allowed") {
    return (
      <Notice tone="warning" label="Not allowed yet" announce>
        <p>Allow CFOKit in this company to keep your books from here, then ask again.</p>
        <div className="pt-2">
          <Button
            variant="primary"
            onClick={() => void navigate({ to: "/agents/$agent", params: { agent: AGENT } })}
          >
            Allow CFOKit
          </Button>
        </div>
      </Notice>
    );
  }
  if (code === "agent_off") {
    return (
      <Notice tone="neutral" label="Chat is off" announce>
        This deployment has no inference credential, so CFOKit cannot answer here. Ask your own
        agent instead, or set ANTHROPIC_API_KEY for the agent service.
      </Notice>
    );
  }
  return (
    <Notice tone="danger" label="Refused" announce>
      {message || "CFOKit could not answer. Try again."}
    </Notice>
  );
}

/** One conversation, live: history from the agent, each turn streamed from it (ADR-0075 § 1). */
function Live({
  agentUrl,
  entityId,
  conversationId,
  draft,
}: {
  agentUrl: string;
  entityId: string;
  conversationId: string;
  draft: string | undefined;
}) {
  const token = useAuth().user?.access_token;
  const [refused, setRefused] = useState<{ code: string; message: string } | null>(null);
  const path = `${agentUrl}/entities/${encodeURIComponent(entityId)}/conversations/${encodeURIComponent(conversationId)}`;
  const headers = useMemo<Record<string, string>>(
    () => (token === undefined ? {} : { authorization: `Bearer ${token}` }),
    [token],
  );
  const agent = useMemo(
    () => new HttpAgent({ url: `${path}/turn`, headers, threadId: conversationId }),
    [path, headers, conversationId],
  );
  const runtime = useAgUiRuntime({
    agent,
    onError: (error) => setRefused(refusalOf(error)),
    adapters: {
      history: {
        // What the agent kept, converted by the agent to the protocol this window speaks; a
        // reload or a reconnect shows everything up to the last completed message (ADR-0075 § 1).
        async load() {
          const response = await fetch(path, { headers });
          const body: unknown = await response.json().catch(() => null);
          if (!response.ok) {
            setRefused(refusalOf({ payload: body }));
            return { messages: [] };
          }
          return { messages: thread((body as { messages: AgUiMessage[] }).messages) };
        },
        async append() {
          // The agent keeps every message itself, in core; nothing is stored here.
        },
      },
    },
  });

  // A question handed over by another page waits in the composer for the person to send.
  useEffect(() => {
    if (draft !== undefined) runtime.thread.composer.setText(draft);
  }, [runtime, draft]);

  // A refusal stands until the person tries again: a new turn clears it, and refuses afresh if it
  // still applies.
  useEffect(
    () =>
      runtime.thread.subscribe(() => {
        if (runtime.thread.getState().isRunning) setRefused(null);
      }),
    [runtime],
  );

  // A stream keeps the agent's instance billed while it is open, so a hidden tab stops its turn
  // (ADR-0075, Consequences); what completed is kept, and the person asks again to go on.
  useEffect(() => {
    function hidden() {
      if (document.visibilityState === "hidden") runtime.thread.cancelRun();
    }
    document.addEventListener("visibilitychange", hidden);
    return () => document.removeEventListener("visibilitychange", hidden);
  }, [runtime]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {refused !== null && <Refusal {...refused} />}
      <Conversation runtime={runtime} placeholder="Ask about your books" />
    </div>
  );
}

/**
 * The chat with CFOKit's agent in a company (ADR-0075). With no conversation named, it opens the
 * person's newest, or starts one, and puts its ID in the URL, so a reload lands on the same
 * conversation (ADR-0049 § 2).
 */
export function ChatPage({
  entityId,
  conversationId,
  draft,
}: {
  entityId: string;
  conversationId?: string | undefined;
  /** A question to leave in the composer, unsent, such as getting started's first question. */
  draft?: string | undefined;
}) {
  const api = useApi();
  const navigate = useNavigate();
  const company = useCompanyName(api, entityId, useStarted().company);
  const agentUrl = useAgentUrl();
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    if (conversationId !== undefined) return;
    let current = true;
    const companies = `/entities/${encodeURIComponent(entityId)}/conversations`;
    (async () => {
      const { conversations } = await api.get<{ conversations: { conversation_id: string }[] }>(
        companies,
      );
      const id =
        conversations[0]?.conversation_id ??
        (
          await api.post<{ conversation_id: string }>(
            companies,
            {},
            {
              "Idempotency-Key": crypto.randomUUID(),
            },
          )
        ).conversation_id;
      if (current) {
        void navigate({
          to: "/companies/$entityId/chat/$conversationId",
          params: { entityId, conversationId: id },
          search: draft === undefined ? {} : { draft },
          replace: true,
        });
      }
    })().catch((error: unknown) => {
      if (current) setFailed(error instanceof ApiError ? error.message : String(error));
    });
    return () => {
      current = false;
    };
  }, [api, entityId, conversationId, draft, navigate]);

  let body;
  if (agentUrl === undefined) {
    body = (
      <Notice tone="neutral" label="No chat here">
        This deployment does not run CFOKit's agent.{" "}
        <TextLink href="/app/settings">Connect your own agent</TextLink> to ask about your books.
      </Notice>
    );
  } else if (failed !== null) {
    body = (
      <Notice tone="danger" label="Refused" announce>
        {failed}
      </Notice>
    );
  } else if (agentUrl === null || conversationId === undefined) {
    body = <p className="text-body text-ink-muted">Opening the conversation…</p>;
  } else {
    body = (
      <Live
        key={conversationId}
        agentUrl={agentUrl}
        entityId={entityId}
        conversationId={conversationId}
        draft={draft}
      />
    );
  }

  return (
    <PersonFrame company={company}>
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        <h1 className="font-display text-heading text-ink">Ask CFOKit</h1>
        {body}
      </div>
    </PersonFrame>
  );
}

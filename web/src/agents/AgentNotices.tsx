import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useApi } from "../api";
import { Button, Notice } from "../components";
import type { Notification } from "../questions/QuestionsPage";
import { dismissalKey } from "../questions/QuestionsPage";
import type { Company } from "../settings/SettingsPage";
import { describeAgent, signedInAs, type AgentConnection } from "./name";

/** The class raised to a company's other administrators when an agent is allowed there. */
export const AGENT_ALLOWED = "agent_allowed";

interface AgentNotice {
  notification: Notification;
  company: Company;
  connection: AgentConnection | undefined;
}

/**
 * Each company's open notices that someone else allowed an agent there (ADR-0066 § 6), with what
 * the agent reported and the member account it signed in as. Read company by company, under each
 * company's own scope; a company that refuses the read has none to show.
 */
function useAgentNotices(companies: Company[]) {
  const api = useApi();
  const [notices, setNotices] = useState<AgentNotice[]>([]);
  useEffect(() => {
    let current = true;
    Promise.all(
      companies.map(async (company): Promise<AgentNotice[]> => {
        const at = `/entities/${encodeURIComponent(company.id)}`;
        const open = await api
          .get<{ notifications?: Notification[] }>(`${at}/notifications`)
          .then((answer) =>
            (answer.notifications ?? []).filter((n) => n.notification_class === AGENT_ALLOWED),
          )
          .catch(() => []);
        if (open.length === 0) return [];
        const agents = await api
          .get<{ agents?: AgentConnection[] }>(`${at}/agents`)
          .then((answer) => answer.agents ?? [])
          .catch(() => []);
        return open.map((notification) => ({
          notification,
          company,
          connection: agents.find((found) => found.agent_id === notification.subject_ref),
        }));
      }),
    )
      .then((found) => {
        if (current) setNotices(found.flat());
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [api, companies]);
  return [notices, setNotices] as const;
}

/** Tells an administrator that someone else allowed an agent in one of their companies. */
export function AgentNotices({ companies }: { companies: Company[] }) {
  const api = useApi();
  const navigate = useNavigate();
  const [notices, setNotices] = useAgentNotices(companies);
  const [dismissing, setDismissing] = useState<string | null>(null);

  async function dismiss({ notification, company }: AgentNotice) {
    setDismissing(notification.notification_id);
    try {
      await api.post(
        `/entities/${encodeURIComponent(company.id)}/notifications/` +
          `${encodeURIComponent(notification.notification_id)}/dismissal`,
        {},
        { "Idempotency-Key": dismissalKey(notification.notification_id) },
      );
      setNotices((was) =>
        was.filter((n) => n.notification.notification_id !== notification.notification_id),
      );
    } finally {
      setDismissing(null);
    }
  }

  if (notices.length === 0) return null;
  return (
    <ul aria-label="Agents allowed by others" className="flex flex-col gap-3">
      {notices.map((notice) => {
        const agent = notice.notification.subject_ref;
        const account = notice.connection === undefined ? null : signedInAs(notice.connection);
        return (
          <li key={notice.notification.notification_id}>
            <Notice tone="warning" label="Agent allowed">
              <p>
                {describeAgent(agent, notice.connection)}
                {account === null ? "" : `, signed in as ${account},`} was allowed in{" "}
                {notice.company.name}. Revoke it there if you do not recognize it.
              </p>
              <div className="-mx-3 flex flex-wrap gap-2">
                <Button
                  variant="link"
                  onClick={() => void navigate({ to: "/agents/$agent", params: { agent } })}
                >
                  Review
                </Button>
                <Button
                  variant="link"
                  disabled={dismissing === notice.notification.notification_id}
                  onClick={() => void dismiss(notice)}
                >
                  Dismiss
                </Button>
              </div>
            </Notice>
          </li>
        );
      })}
    </ul>
  );
}

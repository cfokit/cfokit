import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useApi, type Api } from "../api";
import {
  AppFrame,
  Button,
  CopyBlock,
  MoneyTable,
  Notice,
  TextLink,
  type Column,
  type Row,
} from "../components";
import { claudeLink } from "../start/FirstQuestion";
import { personName } from "../start/StartFrame";
import { useStarted } from "../start/state";

/** A line no rule resolved and nothing has answered since (`BKP-12`), as the API lists it. */
export interface Unresolved {
  source_ref: string;
  transaction_id: string;
  decision_id: string;
  payee: string;
  description: string;
  amount: string;
  commodity: string;
  source_account_id: string;
  transaction_date: string;
  source_kind: string;
}

/** One of the signed-in person's open notifications in this company. */
export interface Notification {
  notification_id: string;
  entity_id: string;
  notification_class: string;
  subject_ref: string;
  link: string;
  raised_at: string;
}

/**
 * What to ask Claude, naming the company: every call names its entity and there is no current
 * one (the bookkeeper skill).
 */
export function unresolvedQuestion(company: string, entityId: string): string {
  const which = company === "" ? `entity ${entityId}` : `"${company}" (entity ${entityId})`;
  return (
    `I have transactions in ${which} that CFOKit couldn't categorize. Show me the unresolved ` +
    `ones and help me set up rules for them.`
  );
}

/**
 * Dismissing the same notification twice is one dismissal: the key is the notification's own,
 * so a retry after a dropped answer replays rather than acts again (ADR-0029).
 */
export function dismissalKey(notificationId: string): string {
  return `dismissal:${notificationId}`;
}

type Loaded =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "ready"; unresolved: Unresolved[]; notifications: Notification[] };

function useQuestions(api: Api, entityId: string) {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  useEffect(() => {
    let current = true;
    const at = `/entities/${encodeURIComponent(entityId)}`;
    Promise.all([
      api.get<{ unresolved: Unresolved[] }>(`${at}/unresolved-transactions`),
      api.get<{ notifications: Notification[] }>(`${at}/notifications`),
    ])
      .then(([lines, open]) => {
        if (current) {
          setLoaded({
            state: "ready",
            unresolved: lines.unresolved,
            notifications: open.notifications.filter(
              (n) => n.notification_class === "unresolved_transaction",
            ),
          });
        }
      })
      .catch((error: unknown) => {
        if (current) {
          setLoaded({
            state: "failed",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      current = false;
    };
  }, [api, entityId]);
  return [loaded, setLoaded] as const;
}

const COLUMNS: Column[] = [
  { key: "payee", header: "Payee", kind: "text" },
  { key: "date", header: "Date", kind: "text" },
  { key: "description", header: "Description", kind: "text" },
  { key: "amount", header: "Amount", kind: "money" },
];

function transactions(count: number): string {
  return count === 1 ? "1 transaction" : `${count} transactions`;
}

/**
 * What CFOKit is asking the signed-in person about this company: the lines no rule resolved
 * (`BKP-12`). Every `unresolved_transaction` notification links here. They are answered in
 * Claude, by approving a rule and running assignment again (`BKP-09`), not on this page; what the
 * page does itself is dismiss a notification, which is the person's own act (ADR-0056 § 2).
 */
export function QuestionsPage({ entityId }: { entityId: string }) {
  const auth = useAuth();
  const api = useApi();
  const { company } = useStarted();
  const [loaded, setLoaded] = useQuestions(api, entityId);
  const [dismissing, setDismissing] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const prompt = unresolvedQuestion(company, entityId);

  async function dismiss(notification: Notification) {
    setDismissing(notification.notification_id);
    setRefused(null);
    try {
      await api.post(
        `/entities/${encodeURIComponent(entityId)}/notifications/` +
          `${encodeURIComponent(notification.notification_id)}/dismissal`,
        {},
        { "Idempotency-Key": dismissalKey(notification.notification_id) },
      );
      setLoaded((was) =>
        was.state === "ready"
          ? {
              ...was,
              notifications: was.notifications.filter(
                (n) => n.notification_id !== notification.notification_id,
              ),
            }
          : was,
      );
    } catch (error) {
      setRefused(error instanceof Error ? error.message : String(error));
    } finally {
      setDismissing(null);
    }
  }

  return (
    <AppFrame
      company={company}
      person={personName(auth.user?.profile)}
      onSignOut={() => void auth.signoutRedirect()}
    >
      <div className="flex flex-col gap-6">
        <h1 className="font-display text-display-compact text-ink tablet:text-display">
          Questions for you
        </h1>
        {loaded.state === "loading" && (
          <Notice tone="neutral" label="Reading your questions">
            Finding the transactions waiting for you…
          </Notice>
        )}
        {loaded.state === "failed" && (
          <Notice tone="danger" label="Couldn't read your questions" announce>
            {loaded.message}. Reload the page to try again.
          </Notice>
        )}
        {loaded.state === "ready" && loaded.unresolved.length === 0 && (
          <Notice tone="success" label="Nothing waiting">
            Every transaction is categorized. When no rule covers one, it shows up here.
          </Notice>
        )}
        {loaded.state === "ready" && loaded.unresolved.length > 0 && (
          <>
            <p className="max-w-reading-max text-body text-ink">
              CFOKit couldn&apos;t categorize {transactions(loaded.unresolved.length)}: no rule
              covers {loaded.unresolved.length === 1 ? "it" : "them"} yet. You answer these in
              Claude, by approving a rule that covers them; Claude then books them. Nothing on this
              page changes your books.
            </p>
            <div>
              <Button variant="primary" onClick={() => window.location.assign(claudeLink(prompt))}>
                Continue in Claude
              </Button>
            </div>
            <CopyBlock label="Or paste this into Claude" text={prompt} />
            <p className="max-w-reading-max text-body text-ink">
              Claude not connected to CFOKit yet?{" "}
              <TextLink href={`/app/companies/${encodeURIComponent(entityId)}/connect`}>
                Connect Claude
              </TextLink>
            </p>
            {refused !== null && (
              <Notice tone="danger" label="Not dismissed" announce>
                {refused}. Try again.
              </Notice>
            )}
            <Lines
              unresolved={loaded.unresolved}
              notifications={loaded.notifications}
              dismissing={dismissing}
              onDismiss={(n) => void dismiss(n)}
            />
            <p className="max-w-reading-max text-caption text-ink-muted">
              Dismissing a notification stops it reminding you. The transaction stays here until it
              is categorized.
            </p>
          </>
        )}
      </div>
    </AppFrame>
  );
}

interface LinesProps {
  unresolved: Unresolved[];
  notifications: Notification[];
  dismissing: string | null;
  onDismiss: (notification: Notification) => void;
}

/** The lines, one table per currency, since a table shows its currency once. */
function Lines({ unresolved, notifications, dismissing, onDismiss }: LinesProps) {
  const about = new Map(notifications.map((n) => [n.subject_ref, n]));
  const commodities = [...new Set(unresolved.map((line) => line.commodity))];
  return (
    <>
      {commodities.map((commodity) => {
        const rows: Row[] = unresolved
          .filter((line) => line.commodity === commodity)
          .map((line) => {
            const name = line.payee === "" ? line.description : line.payee;
            const notification = about.get(line.source_ref);
            return {
              id: line.source_ref,
              cells: {
                payee: name,
                date: line.transaction_date,
                description: line.payee === "" ? "" : line.description,
                amount: line.amount,
              },
              action:
                notification === undefined ? undefined : (
                  <Button
                    variant="link"
                    aria-label={`Dismiss the notification about ${name}, ${line.transaction_date}`}
                    disabled={dismissing === notification.notification_id}
                    onClick={() => onDismiss(notification)}
                  >
                    Dismiss
                  </Button>
                ),
            };
          });
        return (
          <MoneyTable
            key={commodity}
            caption={
              commodities.length === 1
                ? "Transactions waiting for a rule"
                : `Transactions waiting for a rule, ${commodity}`
            }
            currency={commodity}
            columns={COLUMNS}
            rows={rows}
          />
        );
      })}
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { useApi, type Api } from "../api";
import {
  Button,
  CopyBlock,
  MoneyTable,
  Notice,
  TextLink,
  type Column,
  type Row,
} from "../components";
import { claudeLink } from "../start/FirstQuestion";
import { PersonFrame } from "../settings/PersonFrame";
import { useStarted } from "../start/state";

/** A record already in the books that a line could be (ADR-0059), as the API lists it. */
export interface Counterpart {
  kind: "obligation" | "transaction" | "transfer";
  id: string;
  account_id: string;
  amount: string;
  commodity: string;
  date: string;
}

/**
 * A line waiting on the person (`BKP-12`), as the API lists it: `unmatched` when no rule covers
 * it, `ambiguous` when more than one record in the books fits it, `proposed` when it pays an open
 * invoice and waits to be confirmed. The last two carry the records in `counterparts`.
 */
export interface Unresolved {
  source_ref: string;
  transaction_id: string;
  decision_id: string;
  outcome?: "unmatched" | "ambiguous" | "proposed";
  payee: string;
  description: string;
  amount: string;
  commodity: string;
  source_account_id: string;
  transaction_date: string;
  source_kind: string;
  counterparts?: Counterpart[];
}

/** What the line waits on, in the person's words. */
export function waitingOn(line: Unresolved): string {
  switch (line.outcome) {
    case "ambiguous":
      return "Your choice of match";
    case "proposed":
      return "Your confirmation";
    default:
      return "A rule";
  }
}

const RECORD: Record<Counterpart["kind"], string> = {
  obligation: "Open invoice",
  transaction: "Entry already recorded",
  transfer: "Other side of a transfer",
};

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
    `ones and help me answer them.`
  );
}

/**
 * Dismissing the same notification twice is one dismissal: the key is the notification's own,
 * so a retry after a dropped answer replays rather than acts again (ADR-0029).
 */
export function dismissalKey(notificationId: string): string {
  return `dismissal:${notificationId}`;
}

/** What the company declared when it was created, as `GET /entities/{entity_id}` returns it. */
export interface Entity {
  id: string;
  slug: string;
  name: string;
  accounting_basis: string;
  fiscal_year_end_month: number;
  fiscal_year_end_day: number;
  functional_currency: string;
  time_zone: string;
}

type Loaded =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "ready"; unresolved: Unresolved[]; notifications: Notification[] };

/**
 * The two lists, read on arrival and again whenever the tab becomes visible: the person answers
 * in Claude, then comes back here, and should see what is still waiting rather than what was.
 * A re-read keeps what is shown until it has something newer, and a failed one keeps it too.
 */
function useQuestions(api: Api, entityId: string) {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const latest = useRef(0);
  useEffect(() => {
    let current = true;
    const at = `/entities/${encodeURIComponent(entityId)}`;
    function read() {
      const reading = ++latest.current;
      const answered = () => current && reading === latest.current;
      Promise.all([
        api.get<{ unresolved: Unresolved[] }>(`${at}/unresolved-transactions`),
        api.get<{ notifications: Notification[] }>(`${at}/notifications`),
      ])
        .then(([lines, open]) => {
          if (answered()) {
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
          if (answered()) {
            setLoaded((was) =>
              was.state === "ready"
                ? was
                : {
                    state: "failed",
                    message: error instanceof Error ? error.message : String(error),
                  },
            );
          }
        });
    }
    function returned() {
      if (document.visibilityState === "visible") read();
    }
    read();
    document.addEventListener("visibilitychange", returned);
    return () => {
      current = false;
      document.removeEventListener("visibilitychange", returned);
    };
  }, [api, entityId]);
  return [loaded, setLoaded] as const;
}

/**
 * The company's name, from the books rather than from getting started's memory, so a reload or
 * a link from a notification still names it. Until it arrives, or if it cannot be read, whatever
 * getting started knew stands in, which may be nothing.
 */
function useCompanyName(api: Api, entityId: string, known: string): string {
  const [name, setName] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    api
      .get<Entity>(`/entities/${encodeURIComponent(entityId)}`)
      .then((entity) => {
        if (current) setName(entity.name);
      })
      .catch(() => {
        // The questions are still worth showing without the company's name.
      });
    return () => {
      current = false;
    };
  }, [api, entityId]);
  return name ?? known;
}

const COLUMNS: Column[] = [
  { key: "payee", header: "Payee", kind: "text" },
  { key: "date", header: "Date", kind: "text" },
  { key: "description", header: "Description", kind: "text" },
  { key: "waiting", header: "Waiting on", kind: "text" },
  { key: "amount", header: "Amount", kind: "money" },
];

const CANDIDATE_COLUMNS: Column[] = [
  { key: "line", header: "Transaction", kind: "text" },
  { key: "record", header: "Could be", kind: "text" },
  { key: "date", header: "Dated", kind: "text" },
  { key: "amount", header: "Amount", kind: "money" },
];

function transactions(count: number): string {
  return count === 1 ? "1 transaction" : `${count} transactions`;
}

/**
 * What CFOKit is asking the signed-in person about this company: the lines no rule resolved, and
 * those that fit more than one record in the books or pay an open invoice, with the records they
 * could be (`BKP-12`, ADR-0059 § 4). Every `unresolved_transaction` notification links here. They
 * are answered in Claude — by approving a rule (`BKP-09`), or by the person naming the record a
 * line is — not on this page; what the page does itself is dismiss a notification, which is the
 * person's own act (ADR-0056 § 2).
 */
export function QuestionsPage({ entityId }: { entityId: string }) {
  const api = useApi();
  const started = useStarted();
  const company = useCompanyName(api, entityId, started.company);
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
    <PersonFrame company={company}>
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
              CFOKit couldn&apos;t categorize {transactions(loaded.unresolved.length)}. You answer
              these in Claude: by approving a rule that covers a transaction, or by saying which
              record already in your books it is, or that it is none of them. Claude then books
              them. Nothing on this page changes your books.
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
    </PersonFrame>
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
                waiting: waitingOn(line),
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
        // The records each line could be, as the API listed them: the candidates of an ambiguous
        // line, or the invoice a proposed one pays (ADR-0059 § 4).
        const candidates: Row[] = unresolved
          .filter((line) => line.commodity === commodity)
          .flatMap((line) =>
            (line.counterparts ?? []).map((counterpart) => ({
              id: `${line.source_ref}:${counterpart.kind}:${counterpart.id}`,
              cells: {
                line: `${line.payee === "" ? line.description : line.payee}, ${line.transaction_date}`,
                record: RECORD[counterpart.kind],
                date: counterpart.date,
                amount: counterpart.amount,
              },
            })),
          );
        const suffix = commodities.length === 1 ? "" : `, ${commodity}`;
        return (
          <div key={commodity} className="flex flex-col gap-6">
            <MoneyTable
              caption={`Transactions waiting for you${suffix}`}
              currency={commodity}
              columns={COLUMNS}
              rows={rows}
            />
            {candidates.length > 0 && (
              <MoneyTable
                caption={`Records already in your books they could be${suffix}`}
                currency={commodity}
                columns={CANDIDATE_COLUMNS}
                rows={candidates}
              />
            )}
          </div>
        );
      })}
    </>
  );
}

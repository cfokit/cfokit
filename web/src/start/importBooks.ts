import type { Api } from "../api";
import type { SourceBooks } from "../quickbooks/read";

// Entries per request. Small enough that each request is short and progress moves steadily; a
// company's whole journal in one request is the shape the three calls exist to avoid.
export const BATCH = 500;

export interface Refusal {
  reference: string;
  date: string | null;
  code: string;
  detail: string;
}

export interface Divergence {
  account_code: string;
  ours: string;
  theirs: string;
}

/** What `POST …/reconciliation` answers: the books against the figures QuickBooks states (`IMP-08`). */
export interface Reconciliation {
  agreed: number;
  compared: number;
  journal_total: {
    stated_debits: string;
    stated_credits: string;
    our_debits: string;
    our_credits: string;
    agrees: boolean;
    difference: string;
  } | null;
  divergences_net_to_zero: boolean;
  divergences: Divergence[];
}

export interface Imported {
  accountsCreated: number;
  posted: number;
  /** Entries an earlier attempt had already posted. Never summed with `posted`. */
  replayed: number;
  refusals: Refusal[];
  reconciliation: Reconciliation;
}

/**
 * Import the books into the entity: open the import and its chart, post the entries in batches,
 * then reconcile against the figures the source states for itself.
 *
 * **Safe to run again.** Each entry's idempotency key is derived from the file's fingerprint and
 * the entry's reference (ADR-0029), so a run that stopped partway resumes by running again: what
 * landed before comes back as `replayed`.
 */
export async function importBooks(
  api: Api,
  entityId: string,
  books: SourceBooks,
  onProgress: (done: number) => void,
): Promise<Imported> {
  const base = `/entities/${encodeURIComponent(entityId)}/imports`;
  const opened = await api.post<{ import_id: string; accounts_created: number }>(base, {
    shape_version: books.shape_version,
    system: books.system,
    fingerprint: books.fingerprint,
    basis: books.basis,
    balances_basis: books.balances_basis,
    commodity: books.commodity,
    accounts: books.accounts,
  });
  const at = `${base}/${encodeURIComponent(opened.import_id)}`;

  let posted = 0;
  let replayed = 0;
  const refusals: Refusal[] = [];
  for (let start = 0; start < books.entries.length; start += BATCH) {
    const batch = books.entries.slice(start, start + BATCH);
    const done = await api.post<{ posted: number; replayed: number; refusals: Refusal[] }>(
      `${at}/entries`,
      { system: books.system, fingerprint: books.fingerprint, entries: batch },
    );
    posted += done.posted;
    replayed += done.replayed;
    refusals.push(...done.refusals);
    onProgress(start + batch.length);
  }

  const reconciliation = await api.post<Reconciliation>(`${at}/reconciliation`, {
    balances: books.balances,
    journal_total: books.journal_total,
    statements: books.statements,
  });
  return { accountsCreated: opened.accounts_created, posted, replayed, refusals, reconciliation };
}

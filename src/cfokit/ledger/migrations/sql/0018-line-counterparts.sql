-- A line is matched to what the books already hold before any rule codes it (ADR-0059).
--
-- Assignment searches the books for a counterpart — an open obligation, a recorded
-- transaction, or the other side of a transfer — in the same transaction as the write, and
-- records what it found on the decision. Three outcomes join `assigned` and `unmatched`; the
-- counterparts found are stored beside the decision with a digest over them, so replay can
-- rebuild them and re-decide the whole fate; and a leg is claimed by at most one line.
--
-- Nothing is deployed, so the new NOT NULL column takes no default: there is no population of
-- decisions predating it and no honest value to backfill.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

-- ---------------------------------------------------------------------------
-- The decision's outcome gains the three the search produces (ADR-0059 § 5).
--
-- * `matched` — exactly one counterpart, acted on: a settlement, nothing new, or a transfer.
-- * `proposed` — an uploaded line whose sole counterpart is an open obligation. A question a
--   person confirms, because ADR-0047 forbids posting what the session that read the document
--   asked for, and a settlement needs its transaction posted.
-- * `ambiguous` — two or more counterparts. A question, because no order among them is stated.
-- ---------------------------------------------------------------------------
ALTER TABLE assignment_decision DROP CONSTRAINT assignment_decision_outcome_check;
ALTER TABLE assignment_decision ADD CONSTRAINT assignment_decision_outcome_check
    CHECK (outcome IN ('assigned', 'unmatched', 'matched', 'proposed', 'ambiguous'));

-- `BKP-12`'s worklist is every kind of question now, not only the line no rule resolved.
DROP INDEX assignment_decision_unmatched_idx;
CREATE INDEX assignment_decision_question_idx ON assignment_decision (entity_id, decided_at)
    WHERE outcome IN ('unmatched', 'ambiguous', 'proposed');

-- ---------------------------------------------------------------------------
-- Identical facts are not an identical movement: two coffees on one statement are two lines
-- (ADR-0029). The fingerprint was stored for the duplicate question, and is not what answers
-- it — the search over the books is, and a claimed leg is never a counterpart. Removed.
-- ---------------------------------------------------------------------------
ALTER TABLE assignment_decision DROP COLUMN candidate_fingerprint;

-- ---------------------------------------------------------------------------
-- What the search saw, made checkable, beside the rule-set digest (ADR-0059 § 5).
--
-- sha256 over a canonical rendering of the counterparts stored below — none, one or all of
-- them. Everything the search reads is append-only and timestamped, so the counterparts as they
-- stood at `decided_at` are a reconstruction. Replay rebuilds them and compares this; where it
-- disagrees the books changed and the decision is not compared, and where it agrees the whole
-- fate — search, then rules — is re-decided.
-- ---------------------------------------------------------------------------
ALTER TABLE assignment_decision
    ADD COLUMN counterpart_digest text NOT NULL
        CHECK (counterpart_digest ~ '^[0-9a-f]{64}$');

-- A person's choice (ADR-0059 § 4, ADR-0042): naming a counterpart, or none so the rules
-- decide. Recorded because a choice is not a function of the inputs, so replay counts it rather
-- than re-deciding it. Null for every decision the matcher took by itself.
ALTER TABLE assignment_decision
    ADD COLUMN chosen_by text CHECK (chosen_by IS NULL OR length(trim(chosen_by)) > 0);

-- The earlier side of a transfer is decided by the line that arrived second: one transaction
-- with both legs, and two decisions (ADR-0059 § 3). This names the arriving line's decision on
-- the earlier line's, so replay re-decides the pair once, through the line whose search found
-- it, rather than asking the earlier line's search to find a line that had not yet arrived.
ALTER TABLE assignment_decision
    ADD COLUMN decided_with_decision_id uuid REFERENCES assignment_decision (id);

-- ---------------------------------------------------------------------------
-- **A leg is claimed by at most one line** (ADR-0059 § 1). The search and the write are one
-- transaction under the entity's lock, so two runs cannot claim one counterpart; this is the
-- second enforcement point. A decision's transaction and the account its line arrived on name
-- the leg the line explains.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX assignment_decision_claims_one_leg
    ON assignment_decision (transaction_id, candidate_source_account_id);

-- ---------------------------------------------------------------------------
-- The counterparts a decision found, as they stood when it was taken: one for `matched` and
-- `proposed`, every one for `ambiguous`, none otherwise (ADR-0059 § 5).
--
-- Columns rather than jsonb, for the reason the candidate's facts are columns (0012): the set
-- is closed. `counterpart_id` is opaque — an obligation's, a transaction's, or for the other
-- side of a transfer the other line's decision — because it names one of three tables.
-- ---------------------------------------------------------------------------
CREATE TABLE assignment_decision_counterpart (
    id               uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        uuid           NOT NULL REFERENCES entity (id),
    decision_id      uuid           NOT NULL REFERENCES assignment_decision (id),
    -- Canonical order, the order the digest is computed in.
    position         smallint       NOT NULL CHECK (position > 0),
    kind             text           NOT NULL
                                    CHECK (kind IN ('obligation', 'transaction', 'transfer')),
    counterpart_id   uuid           NOT NULL,
    -- The account the counterpart is on: the obligation's carrying account, the line's own for a
    -- recorded transaction, the other line's for a transfer.
    account_id       uuid           NOT NULL REFERENCES account (id),
    -- Signed as a posting is: the obligation's outstanding amount, the posting's, or the other
    -- line's.
    amount           numeric(28,10) NOT NULL CHECK (amount <> 0),
    commodity        text           NOT NULL,
    -- When the obligation arose, the transaction is dated, or the other line is.
    counterpart_date date           NOT NULL,

    UNIQUE (decision_id, position),
    UNIQUE (decision_id, kind, counterpart_id)
);

CREATE INDEX assignment_decision_counterpart_decision_idx
    ON assignment_decision_counterpart (entity_id, decision_id, position);

CREATE TRIGGER assignment_decision_counterpart_append_only
    BEFORE UPDATE OR DELETE ON assignment_decision_counterpart
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

ALTER TABLE assignment_decision_counterpart ENABLE ROW LEVEL SECURITY;

CREATE POLICY assignment_decision_counterpart_entity_isolation
    ON assignment_decision_counterpart
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

GRANT SELECT, INSERT ON assignment_decision_counterpart TO cfokit_app;

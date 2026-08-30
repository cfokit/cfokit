-- 0001 — core double-entry schema.
--
-- Establishes entities, the chart of accounts, transactions, and postings, together with
-- the invariants that make them correct. The invariants are in the database rather than
-- only in application code because a check that lives on one code path is only as reliable
-- as every future code path (ADR-0006).
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.
--
-- Decisions relied on:
--   ADR-0003  Postgres only; row-level security keyed on entity_id
--   ADR-0005  Decimal everywhere; every decimal column is NUMERIC(28,10)
--   ADR-0006  Zero-sum enforced by a deferred constraint trigger, at posting
--   ADR-0007  Immutable at posting; corrections are reversing entries
--   ADR-0012  Idempotency keys; one audit_log row per state change
--   ADR-0014  Two dates per transaction, so backdating is self-identifying
--   REQ-A6    Lots deferred, but the shape is reserved
--   REQ-A8    Accounting basis and fiscal year are entity properties

-- ---------------------------------------------------------------------------
-- Migration bookkeeping. The runner creates this if absent, but declaring it
-- here keeps the schema self-describing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migration (
    version     text        PRIMARY KEY,
    name        text        NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Entities. One deployment holds books for many; nothing crosses the boundary
-- without an explicit grant (REQ-A2).
-- ---------------------------------------------------------------------------
CREATE TABLE entity (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                  text        NOT NULL UNIQUE,
    name                  text        NOT NULL,
    -- REQ-A8: a property of the entity, not a per-report option. Changing it is a
    -- significant event, not a preference.
    accounting_basis      text        NOT NULL CHECK (accounting_basis IN ('cash', 'accrual')),
    fiscal_year_end_month smallint    NOT NULL CHECK (fiscal_year_end_month BETWEEN 1 AND 12),
    fiscal_year_end_day   smallint    NOT NULL CHECK (fiscal_year_end_day BETWEEN 1 AND 31),
    created_at            timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Chart of accounts.
-- ---------------------------------------------------------------------------
CREATE TABLE account (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id  uuid        NOT NULL REFERENCES entity (id),
    code       text        NOT NULL,
    name       text        NOT NULL,
    type       text        NOT NULL CHECK (type IN ('asset', 'liability', 'equity', 'income', 'expense')),
    parent_id  uuid        REFERENCES account (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (entity_id, code)
);

CREATE INDEX account_entity_idx ON account (entity_id);

-- ---------------------------------------------------------------------------
-- Transactions. Named ledger_transaction because `transaction` reads ambiguously
-- next to database transactions in SQL that mixes both.
-- ---------------------------------------------------------------------------
CREATE TABLE ledger_transaction (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        uuid        NOT NULL REFERENCES entity (id),
    -- ADR-0007: posting is the point of no return. Drafts are freely editable.
    status           text        NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'posted')),
    -- ADR-0014: two dates. transaction_date is when it economically occurred;
    -- recorded_at is when it entered the books. Backdating is these diverging, which
    -- makes every backdated entry self-identifying with no flag required. recorded_at
    -- is also what makes "the books as we knew them at T" a plain WHERE clause.
    transaction_date date        NOT NULL,
    recorded_at      timestamptz NOT NULL DEFAULT now(),
    posted_at        timestamptz,
    description      text,
    -- ADR-0007: corrections are reversing entries, and a reversal says what it reverses.
    reverses_id      uuid        REFERENCES ledger_transaction (id),
    CONSTRAINT posted_at_iff_posted CHECK ((status = 'posted') = (posted_at IS NOT NULL))
);

CREATE INDEX ledger_transaction_entity_date_idx
    ON ledger_transaction (entity_id, transaction_date);
-- Supports "as known at T" reporting (ADR-0014).
CREATE INDEX ledger_transaction_recorded_idx ON ledger_transaction (entity_id, recorded_at);

-- ---------------------------------------------------------------------------
-- Postings. Every decimal column is NUMERIC(28,10) (ADR-0005).
-- ---------------------------------------------------------------------------
CREATE TABLE posting (
    id             uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id uuid           NOT NULL REFERENCES ledger_transaction (id),
    entity_id      uuid           NOT NULL REFERENCES entity (id),
    account_id     uuid           NOT NULL REFERENCES account (id),
    amount         numeric(28,10) NOT NULL,
    commodity      text           NOT NULL,
    -- REQ-A6: lot tracking is deferred until an entity holds inventory or investments.
    -- The shape is reserved from the first migration because ADR-0003 already presumes
    -- lot state, and adding these later is a migration on the most-written table.
    -- Nothing populates them yet.
    cost_amount    numeric(28,10),
    cost_commodity text,
    lot_id         uuid,
    created_at     timestamptz    NOT NULL DEFAULT now(),
    CONSTRAINT cost_amount_with_commodity CHECK ((cost_amount IS NULL) = (cost_commodity IS NULL))
);

CREATE INDEX posting_transaction_idx ON posting (transaction_id);
CREATE INDEX posting_account_idx ON posting (entity_id, account_id);

-- ---------------------------------------------------------------------------
-- Audit trail. Exactly one row per state-changing service call (ADR-0012).
-- ---------------------------------------------------------------------------
CREATE TABLE audit_log (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id    uuid        REFERENCES entity (id),
    request_id   text        NOT NULL,
    actor        text        NOT NULL,
    action       text        NOT NULL,
    subject_type text        NOT NULL,
    subject_id   uuid,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    -- Identifiers and counts only. Never posting amounts, account numbers, or payee
    -- names (CLAUDE.md, Observability).
    detail       jsonb
);

CREATE INDEX audit_log_entity_idx ON audit_log (entity_id, occurred_at);
CREATE INDEX audit_log_subject_idx ON audit_log (subject_type, subject_id);

-- ---------------------------------------------------------------------------
-- Idempotency. Mandatory on writes; a replay returns the original result rather
-- than applying the operation again (ADR-0012).
-- ---------------------------------------------------------------------------
CREATE TABLE idempotency_key (
    entity_id    uuid        NOT NULL REFERENCES entity (id),
    key          text        NOT NULL,
    request_hash text        NOT NULL,
    result       jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_id, key)
);

-- ---------------------------------------------------------------------------
-- Zero-sum, enforced at COMMIT by a deferred constraint trigger (ADR-0006).
--
-- Deferred because postings are inserted one row at a time, so a transaction is
-- legitimately unbalanced between the first insert and the last. Checked per
-- commodity, so a multi-currency transaction must balance in each independently.
-- Applies only once posted: a draft may be unbalanced while it is worked on.
-- ---------------------------------------------------------------------------
CREATE FUNCTION assert_posted_transaction_balanced() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    txn_id      uuid;
    unbalanced  record;
BEGIN
    IF TG_TABLE_NAME = 'posting' THEN
        txn_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.transaction_id ELSE NEW.transaction_id END;
    ELSE
        txn_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM ledger_transaction t WHERE t.id = txn_id AND t.status = 'posted'
    ) THEN
        RETURN NULL;
    END IF;

    SELECT p.commodity, SUM(p.amount) AS total
      INTO unbalanced
      FROM posting p
     WHERE p.transaction_id = txn_id
     GROUP BY p.commodity
    HAVING SUM(p.amount) <> 0
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'zero_sum_violated: transaction % is unbalanced in commodity % by %',
            txn_id, unbalanced.commodity, unbalanced.total
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER posting_zero_sum
    AFTER INSERT OR UPDATE OR DELETE ON posting
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION assert_posted_transaction_balanced();

-- Also fires on the draft-to-posted transition, where no posting row changes.
CREATE CONSTRAINT TRIGGER ledger_transaction_zero_sum
    AFTER UPDATE ON ledger_transaction
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION assert_posted_transaction_balanced();

-- ---------------------------------------------------------------------------
-- Append-only from posting (ADR-0007). Enforced here rather than in the service
-- layer because the guarantee is the product; a rule only the application honours
-- is a rule the next bulk-import script will not.
-- ---------------------------------------------------------------------------
CREATE FUNCTION ledger_transaction_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'append_only_violated: transactions are never deleted (id %)', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF OLD.status = 'posted' THEN
        RAISE EXCEPTION
            'append_only_violated: transaction % is posted; correct it with a reversing entry',
            OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.entity_id <> OLD.entity_id OR NEW.recorded_at <> OLD.recorded_at OR NEW.id <> OLD.id THEN
        RAISE EXCEPTION 'append_only_violated: id, entity_id and recorded_at never change'
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER ledger_transaction_append_only
    BEFORE UPDATE OR DELETE ON ledger_transaction
    FOR EACH ROW EXECUTE FUNCTION ledger_transaction_append_only();

CREATE FUNCTION posting_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_status text;
    parent_id     uuid;
BEGIN
    parent_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.transaction_id ELSE NEW.transaction_id END;
    SELECT status INTO parent_status FROM ledger_transaction WHERE id = parent_id;

    IF parent_status = 'posted' THEN
        RAISE EXCEPTION
            'append_only_violated: postings of posted transaction % are immutable', parent_id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER posting_append_only
    BEFORE UPDATE OR DELETE ON posting
    FOR EACH ROW EXECUTE FUNCTION posting_append_only();

-- The audit trail is never rewritten, or it is not a trail.
CREATE FUNCTION audit_log_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append_only_violated: audit_log is insert-only'
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();

-- ---------------------------------------------------------------------------
-- Row-level security keyed on entity_id (ADR-0003).
--
-- NOTE: RLS does not apply to the table owner. The application must connect as a
-- non-owner role and set cfokit.entity_id per transaction, or these policies are
-- inert. That role is a deployment requirement, recorded in infra/README.md.
-- Service-layer filtering is required regardless; RLS is the second layer.
-- ---------------------------------------------------------------------------
ALTER TABLE account            ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_transaction ENABLE ROW LEVEL SECURITY;
ALTER TABLE posting            ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log          ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_key    ENABLE ROW LEVEL SECURITY;

CREATE POLICY account_entity_isolation ON account
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);
CREATE POLICY ledger_transaction_entity_isolation ON ledger_transaction
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);
CREATE POLICY posting_entity_isolation ON posting
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);
CREATE POLICY audit_log_entity_isolation ON audit_log
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);
CREATE POLICY idempotency_key_entity_isolation ON idempotency_key
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

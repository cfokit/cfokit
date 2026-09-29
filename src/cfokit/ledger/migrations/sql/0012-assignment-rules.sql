-- Assignment rules, and the decisions they produce (`BKP-06` to `BKP-12`, `RPT-08`, ADR-0022).
--
-- **These tables are not the ledger's.** The ledger owns the double-entry primitive and
-- "knows nothing about customers, invoices, banks" — and deciding which expense account a
-- card payment belongs in is exactly that kind of knowledge. `cfokit.assignment` owns them,
-- and reaches them through its own repository.
--
-- They live in this schema and in this migration sequence for the reason
-- `0010-customers-and-invoices.sql` gives for receivables: a module is a sibling in the same
-- deployable, sharing one database and one transaction (ADR-0022 § 3, ADR-0023). A decision
-- and the draft it coded must reach one COMMIT — a decision naming a transaction that rolled
-- back, or a draft whose coding no record explains, is the gap `RPT-08` exists to close.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

-- ---------------------------------------------------------------------------
-- A rule, as it stood from one moment onward. Every row is a version, and no row is ever
-- changed: an edit inserts version n+1, and retiring inserts a version marked retired.
--
-- **`BKP-11` is then structural rather than remembered.** "Changing a rule affects future
-- assignments only" holds because the row that decided an old posting is still here,
-- unchanged, and no code path could alter it.
--
-- **There is no `effective_to` and no current-row flag.** The rule set in force at T is a
-- reconstruction — for each `rule_id`, the version with the greatest `effective_from` not
-- after T, kept if active. ADR-0013 settled this shape for the ledger and the argument
-- carries: "bitemporality is free, so nothing is built for it", because nothing is mutated.
-- ---------------------------------------------------------------------------
CREATE TABLE assignment_rule_version (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id      uuid        NOT NULL REFERENCES entity (id),
    -- The rule this is a version of. There is no `assignment_rule` table: a rule has no
    -- properties of its own that an edit does not change, and seniority — the second level
    -- of `BKP-08`'s order — is MIN(effective_from) over this group, which a table would only
    -- duplicate. A first version mints its own.
    rule_id        uuid        NOT NULL,
    -- Monotone per rule, allocated under the entity's advisory lock (ADR-0011). The UNIQUE
    -- below makes a lost race an error rather than a silent overwrite.
    version        integer     NOT NULL CHECK (version > 0),
    -- Retiring and editing are the same act seen from two angles — both change the set from
    -- a moment onward — so they are one mechanism. A `retired_at` on the previous version
    -- would have been an update, and would put the rule set's history in two places.
    status         text        NOT NULL CHECK (status IN ('active', 'retired')),
    -- What the operator calls it. `BKP-08` wants the order *inspectable*, and an order over
    -- anonymous uuids is not. Versioned, so renaming is a rule change and reads as one.
    label          text        NOT NULL CHECK (length(trim(label)) > 0),
    -- The account a match books to. One account, not a split: `BKP-08` says one rule wins,
    -- so a rule claiming several parts of one transaction would need a second ordering rule
    -- nobody has stated. A split (`BKP-05`) is postings, each carrying its own attribution.
    account_id     uuid        REFERENCES account (id),
    -- `BKP-08`'s stated order, lower first. On the version, so reordering is itself a
    -- versioned change and an old decision reconstructs the order actually in force.
    --
    -- Not UNIQUE, and deliberately: uniqueness would have to hold over "the versions in
    -- force at T", which is a projection no constraint can express. The service enforces it
    -- under the entity lock, and the engine's order is total regardless, so determinism
    -- never rests on a constraint the schema cannot keep.
    precedence     integer     NOT NULL,
    -- When this version entered force, and the axis every reconstruction uses. **System
    -- time, not the transaction's date**: `BKP-11` says a rule change affects future
    -- *assignments*, so a backdated transaction coded today is coded by today's rule set.
    -- Server-assigned, for the reason `recorded_at` is (ADR-0013) — a caller who could
    -- choose when a rule entered force could rewrite which rule won a past assignment.
    effective_from timestamptz NOT NULL DEFAULT now(),
    -- `BKP-09`: approval attaches to the rule, and a version exists only once approved,
    -- because a rule nobody approved is not part of any rule set.
    approved_by    text        NOT NULL CHECK (length(trim(approved_by)) > 0),
    approved_at    timestamptz NOT NULL DEFAULT now(),

    UNIQUE (rule_id, version),
    -- An active version books somewhere; a retirement does not. Storing a value that is
    -- ignored is how a reader comes to trust the wrong one.
    CONSTRAINT active_version_books_somewhere CHECK (
        (status = 'active') = (account_id IS NOT NULL)
    )
);

CREATE INDEX assignment_rule_version_asof_idx
    ON assignment_rule_version (entity_id, effective_from, version);
CREATE INDEX assignment_rule_version_rule_idx
    ON assignment_rule_version (rule_id, version DESC);

-- ---------------------------------------------------------------------------
-- What a version matches on: a closed set of fields and operators, ANDed.
--
-- **No OR, no nesting, no regex, no caller-authored expression.** `BKP-07` requires matching
-- on more than the payee, and that is all it requires. Where an operator needs a
-- disjunction they write two rules — which is also the form `BKP-08` can order and `RPT-08`
-- can attribute. A standard expression language was considered and deferred (ADR-0045).
--
-- **Matching is evaluated in the pure engine, never in SQL.** Postgres `lower()` and `ILIKE`
-- follow the database's collation, so the same rule against the same transaction could
-- resolve differently on two deployments — breaking `BKP-06` outright and `EXP-04`'s promise
-- that a receiving deployment resolves every posting to the same rule.
--
-- The CHECK below is the closed set written down, and is verbose on purpose: it is a second
-- enforcement point for the engine's own enumeration, which is one of the provenances
-- ADR-0036 permits for an expected value. A test compares the two.
-- ---------------------------------------------------------------------------
CREATE TABLE assignment_predicate (
    id              uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       uuid           NOT NULL REFERENCES entity (id),
    rule_version_id uuid           NOT NULL REFERENCES assignment_rule_version (id),
    -- Canonical order. An operator reading a rule twice sees its conditions the same way,
    -- and the rule-set digest is computed over a rendering that must not depend on the order
    -- rows came back in.
    position        integer        NOT NULL CHECK (position > 0),
    field           text           NOT NULL,
    operator        text           NOT NULL,
    -- One typed column per value kind rather than one text column parsed on read. A value
    -- stored as text and compared as a number is how a float reaches money (ADR-0005), and
    -- numeric(28,10) is the scale the amount it is compared against is stored at, so the
    -- comparison is exact.
    value_text      text,
    value_numeric   numeric(28,10),
    value_uuid      uuid,

    UNIQUE (rule_version_id, position),

    CONSTRAINT predicate_is_well_typed CHECK (
        -- Free text the source supplies. Most of `BKP-07`'s "more than the payee".
        (   field IN ('payee', 'description')
        AND operator IN ('equals', 'not_equals', 'contains', 'starts_with', 'ends_with')
        AND value_text IS NOT NULL AND value_numeric IS NULL AND value_uuid IS NULL)
        -- Small closed vocabularies, where substring matching would mean nothing.
     OR (   field IN ('commodity', 'direction', 'source_kind')
        AND operator IN ('equals', 'not_equals')
        AND value_text IS NOT NULL AND value_numeric IS NULL AND value_uuid IS NULL)
        -- The amount, signed as a posting is signed: positive is a debit. A threshold is
        -- what `BKP-07` is most often about — the same payee is an expense below a limit
        -- and an asset above it.
     OR (   field = 'amount'
        AND operator IN ('equals', 'not_equals', 'greater_than', 'greater_or_equal',
                         'less_than', 'less_or_equal')
        AND value_numeric IS NOT NULL AND value_text IS NULL AND value_uuid IS NULL)
        -- The entity's own account the movement appeared on. The other discriminator
        -- `BKP-07` needs: one payee is a cost of sale on the trading card and drawings on
        -- the personal one.
     OR (   field = 'source_account_id'
        AND operator IN ('equals', 'not_equals')
        AND value_uuid IS NOT NULL AND value_text IS NULL AND value_numeric IS NULL)
    ),
    CONSTRAINT direction_value_is_known CHECK (
        field <> 'direction' OR value_text IN ('debit', 'credit')
    ),
    CONSTRAINT source_kind_value_is_known CHECK (
        field <> 'source_kind' OR value_text IN ('feed', 'upload', 'manual')
    ),
    -- Normalization happens in the engine before the insert; this catches the part of it
    -- expressible without a collation dependency. A value with stray whitespace matches
    -- nothing and reads as a broken rule rather than a typo.
    CONSTRAINT value_text_is_trimmed CHECK (
        value_text IS NULL OR (value_text = trim(value_text) AND length(value_text) > 0)
    )
);

CREATE INDEX assignment_predicate_version_idx
    ON assignment_predicate (rule_version_id, position);

-- ---------------------------------------------------------------------------
-- One decision per evaluation. This table is `BKP-06`'s acceptance, `BKP-08`'s
-- inspectability, `BKP-12`'s question and `RPT-08`'s trail.
--
-- **The candidate's facts are stored here, as columns.** Replay needs its inputs, and the
-- facts matched on are not the facts booked: a normalized payee and the source kind never
-- reach a posting. A replay reconstructing its inputs from its outputs would be asserting
-- that the code agrees with itself. Columns rather than jsonb because the set is closed,
-- and a jsonb blob would quietly reopen the thing the whole design rests on being closed.
-- ---------------------------------------------------------------------------
CREATE TABLE assignment_decision (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id         uuid        NOT NULL REFERENCES entity (id),
    -- The draft this decision coded, written in the same COMMIT. Not null even when nothing
    -- matched: the honest representation of "we do not know the other side" is a draft that
    -- does not have one. A one-legged draft cannot be posted — the engine's
    -- MINIMUM_POSTINGS is 2 — so the ledger itself refuses to let an unanswered question
    -- become a posting, which is `BKP-12` and `NFR-16` made structural rather than promised.
    transaction_id    uuid        NOT NULL REFERENCES ledger_transaction (id),
    -- The T the rule set was reconstructed at. Server-assigned, and `now()` is transaction
    -- start time; writes for an entity serialize on its advisory lock (ADR-0011), so a rule
    -- version cannot become visible between this and the COMMIT that uses it.
    decided_at        timestamptz NOT NULL DEFAULT now(),
    -- Two outcomes, and nothing between them. There is no `ambiguous`: `BKP-08` makes
    -- overlap a resolved case rather than a question. `BKP-13` and `BKP-14` will extend this
    -- CHECK when they land; a value nobody writes is one every reader has to ask about.
    outcome           text        NOT NULL CHECK (outcome IN ('assigned', 'unmatched')),
    -- `BKP-10`: which rule produced it. The *version*, never the rule — after an edit, a
    -- pointer to the rule would show a reader criteria that were not the ones applied,
    -- which is worse than showing none.
    winning_rule_version_id uuid  REFERENCES assignment_rule_version (id),
    -- `BKP-08`'s "why", at the level that actually settled it. `sole_match` means no
    -- contest; `precedence` means the operator's stated order decided; `seniority` and
    -- `rule_id` mean it did not and the tiebreak did. That last is the one an operator most
    -- needs, because it says the rule set does not state what they think it states — and
    -- finding every such assignment is then a WHERE clause.
    resolved_by       text        CHECK (
                          resolved_by IN ('sole_match', 'precedence', 'seniority', 'rule_id')),
    match_count       smallint    NOT NULL CHECK (match_count >= 0),
    -- **What "an unchanged rule set" means, made checkable.** sha256 over a canonical
    -- rendering of the set in force at `decided_at`. A replay rebuilds that set, recomputes
    -- this, and compares: equal means the set is unchanged and the assignment must reproduce
    -- exactly (`BKP-06`); different means a rule changed, which `BKP-11` permits. Without
    -- it a failed replay cannot tell a determinism defect from an operator editing a rule,
    -- and the acceptance criterion is unfalsifiable.
    rule_set_digest   text        NOT NULL CHECK (rule_set_digest ~ '^[0-9a-f]{64}$'),
    -- Determinism has three inputs, not two: the rule set, the facts, and what the operators
    -- mean. This is the third. A change to normalization or operator semantics makes older
    -- decisions non-comparable, and a replay ignoring that would report a semantic change as
    -- a determinism failure — or silently paper over one. Bumping it needs an ADR.
    evaluator_version smallint    NOT NULL CHECK (evaluator_version > 0),
    -- `BKP-12` answered by `BKP-09`: the operator was asked, approved a rule, and the
    -- candidate was evaluated again. The second decision names the first rather than the
    -- first being updated, because nothing here is updated.
    supersedes_decision_id uuid   REFERENCES assignment_decision (id),

    -- The candidate's facts, exactly the closed set the predicates range over.
    -- Normalized (NFC, case-folded, whitespace collapsed) — the form matching used.
    candidate_payee             text           NOT NULL,
    -- As it arrived. Kept beside the normalized form because an operator reviewing an
    -- assignment needs to see what the bank sent, not what the normalizer made of it.
    candidate_payee_raw         text           NOT NULL,
    candidate_description       text,
    -- Signed as a posting is signed: positive is a debit. `direction` is derived from this
    -- sign rather than stored, because two columns that must agree eventually will not.
    candidate_amount            numeric(28,10) NOT NULL CHECK (candidate_amount <> 0),
    candidate_commodity         text           NOT NULL,
    candidate_source_account_id uuid           NOT NULL REFERENCES account (id),
    candidate_transaction_date  date           NOT NULL,
    candidate_source_kind       text           NOT NULL
                                CHECK (candidate_source_kind IN ('feed', 'upload', 'manual')),
    -- sha256 over the normalized facts. `BKP-13` is "match an incoming transaction to a
    -- record the books already hold", and the cheapest form of that question — the identical
    -- line arriving twice — is this column compared with itself. Written now because the
    -- facts to hash are here now; nothing reads it until `BKP-13` lands.
    candidate_fingerprint       text           NOT NULL
                                CHECK (candidate_fingerprint ~ '^[0-9a-f]{64}$'),

    CONSTRAINT assigned_names_its_rule CHECK (
        (outcome = 'assigned') = (winning_rule_version_id IS NOT NULL)
        AND (outcome = 'assigned') = (resolved_by IS NOT NULL)
        AND (outcome = 'assigned') = (match_count > 0)
    ),
    -- A sole match cannot have been decided by an order, and a contested one cannot have
    -- been a sole match. `resolved_by` is evidence an operator acts on, and evidence that
    -- can disagree with the count beside it is not evidence.
    CONSTRAINT resolution_matches_the_contest CHECK (
        resolved_by IS NULL OR (resolved_by = 'sole_match') = (match_count = 1)
    )
);

CREATE INDEX assignment_decision_transaction_idx
    ON assignment_decision (entity_id, transaction_id);
CREATE INDEX assignment_decision_replay_idx ON assignment_decision (entity_id, decided_at);
-- `BKP-12`'s worklist: what is still unanswered.
CREATE INDEX assignment_decision_unmatched_idx ON assignment_decision (entity_id, decided_at)
    WHERE outcome = 'unmatched';

-- ---------------------------------------------------------------------------
-- The rules that also matched, and where each came in the order.
--
-- `BKP-08`'s acceptance has two halves. "Resolve the same way on every run" is the digest
-- above. "The operator can see which rule won and why" is this: the contest as it stood,
-- stored rather than recomputed, so an operator who reorders next week can still see the
-- order that applied last week — and so the explanation survives a change to the evaluator.
--
-- Only rules that matched. Recording the ones that did not would be a row per rule per
-- transaction, to record an absence the stored set and the stored facts already imply.
-- ---------------------------------------------------------------------------
CREATE TABLE assignment_decision_match (
    id              uuid     PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       uuid     NOT NULL REFERENCES entity (id),
    decision_id     uuid     NOT NULL REFERENCES assignment_decision (id),
    rule_version_id uuid     NOT NULL REFERENCES assignment_rule_version (id),
    -- 1 is the winner. Dense and total, because the order key is total by construction.
    rank            smallint NOT NULL CHECK (rank > 0),
    -- The rendered ordering key this rule sorted on. Stored rather than derived, for the
    -- reason `issued_statement` stores figures: what somebody was told has to survive a
    -- later change in how we would say it.
    order_key       text     NOT NULL CHECK (length(order_key) > 0),

    UNIQUE (decision_id, rank),
    UNIQUE (decision_id, rule_version_id)
);

-- "Which assignments did this rule take part in, and which did it lose?" — the review before
-- editing a rule, and `BKP-11`'s "what will this change affect".
CREATE INDEX assignment_decision_match_rule_idx
    ON assignment_decision_match (entity_id, rule_version_id, rank);

-- ---------------------------------------------------------------------------
-- `BKP-10` and `RPT-08`: attribution on the posting itself.
--
-- **Per posting, not per transaction.** A feed transaction's two legs are decided by
-- different things — the bank leg is the account the feed belongs to and no rule chose it,
-- while the coded leg is the rule's whole output. Attribution on the transaction would claim
-- a rule for a posting no rule touched, and `BKP-05` compounds it: a split coded partly by
-- rule and partly by hand is one transaction with two answers.
--
-- **No foreign key, deliberately.** A REFERENCES to `assignment_rule_version` would make the
-- ledger's schema depend on a module's, which is the one direction ADR-0022 forbids. This is
-- the same opaque pointer `ledger_transaction.decision_record_id` already is, for the same
-- reason, and the integrity it gives up is bought back by the module never deleting a row.
--
-- Nullable, permanently. A hand-entered accrual, an opening balance and a reversal are all
-- postings no rule assigned, and null is the true statement about them. Null is never
-- "unknown": the column ships in the same round as the code that writes it, so there is no
-- population of rule-assigned postings predating it.
-- ---------------------------------------------------------------------------
ALTER TABLE posting ADD COLUMN assigned_by_rule_version_id uuid;

-- The reverse question — "show me everything this rule coded" — which is what an operator
-- wants before editing it (`BKP-11`) and what lets an examiner test a control once rather
-- than per transaction (ADR-0033 § 3).
CREATE INDEX posting_assigned_by_rule_idx
    ON posting (entity_id, assigned_by_rule_version_id)
    WHERE assigned_by_rule_version_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Append-only throughout (ADR-0007), reusing `link_append_only()` from 0008.
--
-- This is what makes the temporal reconstruction sound rather than conventional: "the rule
-- set as it stood at T" is only reproducible while no row that was in it can have changed.
-- ---------------------------------------------------------------------------
CREATE TRIGGER assignment_rule_version_append_only
    BEFORE UPDATE OR DELETE ON assignment_rule_version
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER assignment_predicate_append_only
    BEFORE UPDATE OR DELETE ON assignment_predicate
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER assignment_decision_append_only
    BEFORE UPDATE OR DELETE ON assignment_decision
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER assignment_decision_match_append_only
    BEFORE UPDATE OR DELETE ON assignment_decision_match
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

-- ---------------------------------------------------------------------------
-- Entity isolation, the same second layer every other tenant table has (ADR-0003).
-- ---------------------------------------------------------------------------
ALTER TABLE assignment_rule_version   ENABLE ROW LEVEL SECURITY;
ALTER TABLE assignment_predicate      ENABLE ROW LEVEL SECURITY;
ALTER TABLE assignment_decision       ENABLE ROW LEVEL SECURITY;
ALTER TABLE assignment_decision_match ENABLE ROW LEVEL SECURITY;

CREATE POLICY assignment_rule_version_entity_isolation ON assignment_rule_version
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY assignment_predicate_entity_isolation ON assignment_predicate
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY assignment_decision_entity_isolation ON assignment_decision
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

CREATE POLICY assignment_decision_match_entity_isolation ON assignment_decision_match
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

-- `SELECT, INSERT` and nothing else, the grant 0008 and 0009 use for records written once.
-- No UPDATE as `customer` and `invoice` have (0010), because nothing here has a live phase:
-- a rule is edited by adding a version and a decision is corrected by taking another.
GRANT SELECT, INSERT ON
    assignment_rule_version,
    assignment_predicate,
    assignment_decision,
    assignment_decision_match
TO cfokit_app;

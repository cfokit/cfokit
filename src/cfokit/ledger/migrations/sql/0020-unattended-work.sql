-- Unattended work: a queue of runs, the timers that fill it, and the record of every attempt
-- (`PLT-14`, `PLT-07`, `PLT-18`, ADR-0061).
--
-- **The ledger's tables, with generic columns**, as notifications are (0016). Any module enqueues
-- work in its own act's transaction without depending on another, and the ledger learns no
-- domain meaning from it: a kind, an opaque reference the kind's handler understands, times and
-- states.
--
-- **Read across entities, so no row-level security, and so no content** (ADR-0061 § 6). The pass
-- that claims work has no entity to scope to until it has claimed some. What these tables say is
-- what `entity` already tells every process — which entities exist — plus that one has work due.
-- Never an amount, a payee, an account number, a credential or free text: a failure is recorded
-- by its error code, not its message. Everything a handler reads or writes for the run it claimed
-- is under row-level security for that run's entity.
--
-- The migration runner wraps each file in a transaction; there is no BEGIN/COMMIT here.

-- ---------------------------------------------------------------------------
-- An operational timer: one reference whose kind is checked on an interval the deployment sets,
-- such as a feed's backstop sync (ADR-0061 § 2). Created and ended in the act that creates or
-- ends what it serves. The interval and the reference's offset within it are the kind's and the
-- deployment's, computed by the pass; what is stored is which window was last enqueued, so a
-- pass that comes round twice in one window enqueues once.
-- ---------------------------------------------------------------------------
CREATE TABLE work_schedule (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id         uuid        NOT NULL REFERENCES entity (id),
    kind              text        NOT NULL CHECK (kind ~ '^[a-z][a-z0-9_]{0,62}$'),
    reference         text        NOT NULL CHECK (reference ~ '^[A-Za-z0-9:_-]{1,200}$'),
    created_at        timestamptz NOT NULL DEFAULT now(),
    -- The end of the last window the pass enqueued a run for, or considered and found already
    -- done. Null until the first window has come round.
    last_window_end   timestamptz,
    ended_at          timestamptz
);

-- One live timer per reference.
CREATE UNIQUE INDEX work_schedule_live_idx
    ON work_schedule (entity_id, kind, reference) WHERE ended_at IS NULL;

-- ---------------------------------------------------------------------------
-- One run: a piece of work for one handler, about one reference in one entity.
--
-- `state` moves waiting → running → succeeded, failed or back to waiting for a retry; or waiting
-- → canceled; or into `merged` when a run's work is joined into another waiting one. It is the
-- one mutable column, with the lease and the times that go with it: a queue's row has to change
-- state, and what it did is kept in `work_attempt`, which never changes.
-- ---------------------------------------------------------------------------
CREATE TABLE work_run (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id         uuid        NOT NULL REFERENCES entity (id),
    kind              text        NOT NULL CHECK (kind ~ '^[a-z][a-z0-9_]{0,62}$'),
    reference         text        NOT NULL CHECK (reference ~ '^[A-Za-z0-9:_-]{1,200}$'),
    -- The span the run is for, where its kind has one: the window a backstop came due for, or
    -- the span coalesced runs between them cover. Null for work that is not about a span.
    window_start      timestamptz,
    window_end        timestamptz,
    state             text        NOT NULL DEFAULT 'waiting'
                                  CHECK (state IN ('waiting', 'running', 'succeeded', 'failed',
                                                   'canceled', 'merged')),
    -- Not claimed before this. A retry's backoff moves it later.
    due_at            timestamptz NOT NULL DEFAULT now(),
    enqueued_at       timestamptz NOT NULL DEFAULT now(),
    -- How many attempts have ended, so the next is this plus one.
    attempts          integer     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    -- While running: when the current attempt began, and when the claim lapses if its worker
    -- died. A lapsed claim is due again.
    claimed_at        timestamptz,
    lease_expires_at  timestamptz,
    finished_at       timestamptz,
    -- Where a merged run's work went.
    merged_into       uuid        REFERENCES work_run (id),

    CONSTRAINT a_window_is_ordered CHECK (window_start IS NULL OR window_end IS NULL
                                          OR window_start <= window_end),
    CONSTRAINT running_holds_a_lease CHECK ((state = 'running')
                                            = (lease_expires_at IS NOT NULL)),
    CONSTRAINT merged_names_where CHECK ((state = 'merged') = (merged_into IS NOT NULL))
);

-- At most one waiting run per reference: a cause arriving while one waits joins it (§ 1).
CREATE UNIQUE INDEX work_run_one_waiting_idx
    ON work_run (entity_id, kind, reference) WHERE state = 'waiting';

-- At most one running run per entity. A connection is never synchronized by two runs at once,
-- and one entity's backlog occupies one worker, never every worker (§ 3).
CREATE UNIQUE INDEX work_run_one_running_idx
    ON work_run (entity_id) WHERE state = 'running';

-- The claim reads open runs only. Completed runs are kept as the record of what ran, and this
-- index is what keeps them from slowing the claim as they accumulate.
CREATE INDEX work_run_open_idx
    ON work_run (due_at) WHERE state IN ('waiting', 'running');

-- An entity's own record of what ran for it, in order.
CREATE INDEX work_run_entity_idx ON work_run (entity_id, enqueued_at);

-- ---------------------------------------------------------------------------
-- Why a run exists: each cause that enqueued it or joined it. A run's work is attributable to
-- the schedule window, the request or the provider's notice behind it (`PLT-18`), and a run
-- several causes joined names each of them.
-- ---------------------------------------------------------------------------
CREATE TABLE work_run_cause (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id         uuid        NOT NULL REFERENCES entity (id),
    run_id            uuid        NOT NULL REFERENCES work_run (id),
    cause             text        NOT NULL CHECK (cause IN ('schedule', 'request', 'webhook')),
    -- The schedule's id, the request id, or the delivery's identifier. An identifier, never text
    -- a person or a provider wrote.
    cause_ref         text        NOT NULL CHECK (cause_ref ~ '^[A-Za-z0-9:._-]{1,200}$'),
    caused_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX work_run_cause_run_idx ON work_run_cause (run_id);

-- ---------------------------------------------------------------------------
-- What each attempt did, written when it ended. Never changed.
--
-- `interrupted` is an attempt whose worker stopped without saying how it went — a lapsed lease
-- — written by the pass that found it. Its run is then due again, and runs from the start, which
-- every handler must tolerate (ADR-0029).
-- ---------------------------------------------------------------------------
CREATE TABLE work_attempt (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id         uuid        NOT NULL REFERENCES entity (id),
    run_id            uuid        NOT NULL REFERENCES work_run (id),
    attempt           integer     NOT NULL CHECK (attempt >= 1),
    started_at        timestamptz NOT NULL,
    ended_at          timestamptz NOT NULL,
    outcome           text        NOT NULL CHECK (outcome IN ('succeeded', 'failed',
                                                              'interrupted')),
    -- A failure's stable error code (ADR-0015), never its message: a message can carry what a
    -- provider or a person wrote, and this table is read across entities.
    error_code        text        CHECK (error_code ~ '^[a-z][a-z_]*$'),

    UNIQUE (run_id, attempt),
    CONSTRAINT a_failure_names_its_code CHECK ((outcome = 'failed') = (error_code IS NOT NULL))
);

-- How many runs of a kind began recently, for a kind throttled to a provider's limit.
CREATE INDEX work_attempt_started_idx ON work_attempt (started_at);

CREATE TRIGGER work_run_cause_append_only
    BEFORE UPDATE OR DELETE ON work_run_cause
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

CREATE TRIGGER work_attempt_append_only
    BEFORE UPDATE OR DELETE ON work_attempt
    FOR EACH ROW EXECUTE FUNCTION link_append_only();

-- No DELETE on any of them. A run, once enqueued, is part of the record of what the system did
-- unattended, whatever became of it.
GRANT SELECT, INSERT, UPDATE ON work_schedule, work_run TO cfokit_app;
GRANT SELECT, INSERT ON work_run_cause, work_attempt TO cfokit_app;

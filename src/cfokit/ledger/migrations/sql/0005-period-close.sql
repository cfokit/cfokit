-- Period close and reopen (`LED-11`, ADR-0030, ADR-0027).
--
-- `LED-11`: "A period can be marked closed, signifying it has been reviewed. Once closed, no
-- posting enters the period except through a recorded reopening, and anything so recorded is
-- identifiable as such."
--
-- A close is a row; a reopen updates that row and nothing else, exactly as a grant is revoked
-- rather than deleted (0003). The history is what `SOC1-17` asks an examiner to read: who
-- closed it, who reopened it, when, and why.
--
-- Periods are calendar months, held as (year, month) rather than as a date range, because a
-- range invites two rows that overlap and there is no such thing as half a closed period.
-- ADR-0030's "reopening March reopens March. April stays closed" is why they are discrete
-- rows rather than one closed-through watermark.

CREATE TABLE period_close (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id     uuid        NOT NULL REFERENCES entity (id),
    period_year   int         NOT NULL,
    period_month  int         NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    closed_at     timestamptz NOT NULL DEFAULT now(),
    closed_by     text        NOT NULL,
    -- SOC1-17: reopening "is recorded, and captures the reason". The reason is not optional,
    -- because a reopen without one is indistinguishable from a mistake after the fact.
    reopened_at   timestamptz,
    reopened_by   text,
    reopen_reason text,
    CONSTRAINT reopen_is_recorded_whole CHECK (
        (reopened_at IS NULL) = (reopened_by IS NULL)
        AND (reopened_at IS NULL) = (reopen_reason IS NULL)
    )
);

-- One period is closed at most once at a time. A reopened period may be closed again, so the
-- uniqueness is over the rows still in force rather than over every row ever written.
CREATE UNIQUE INDEX period_close_in_force_idx
    ON period_close (entity_id, period_year, period_month)
    WHERE reopened_at IS NULL;

-- The lookup every posting makes: is this period closed, now.
CREATE INDEX period_close_lookup_idx ON period_close (entity_id, period_year, period_month);

-- ---------------------------------------------------------------------------
-- A close is reopened, never edited and never removed.
-- ---------------------------------------------------------------------------
CREATE FUNCTION period_close_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'append_only_violated: a close is reopened, never deleted (id %)', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.id            <> OLD.id
       OR NEW.entity_id    <> OLD.entity_id
       OR NEW.period_year  <> OLD.period_year
       OR NEW.period_month <> OLD.period_month
       OR NEW.closed_by    <> OLD.closed_by
       OR NEW.closed_at    <> OLD.closed_at
    THEN
        RAISE EXCEPTION
            'append_only_violated: only reopening may change a close (id %)', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF OLD.reopened_at IS NOT NULL THEN
        RAISE EXCEPTION
            'append_only_violated: close % is already reopened', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER period_close_append_only
    BEFORE UPDATE OR DELETE ON period_close
    FOR EACH ROW EXECUTE FUNCTION period_close_append_only();

-- ---------------------------------------------------------------------------
-- Entity isolation, as for every other tenant table (ADR-0003).
-- ---------------------------------------------------------------------------
ALTER TABLE period_close ENABLE ROW LEVEL SECURITY;

CREATE POLICY period_close_entity_isolation ON period_close
    USING (entity_id = current_setting('cfokit.entity_id', true)::uuid);

-- No DELETE: the trigger refuses it and the role does not hold the privilege either.
GRANT SELECT, INSERT, UPDATE ON period_close TO cfokit_app;

-- ---------------------------------------------------------------------------
-- Closing and reopening is its own privilege (ADR-0039: privileges are code, roles are rows).
-- Not `grant`, which is about who reaches the entity; not `post`, because the point of the
-- control is that someone who may post may not decide the books are reviewed.
-- ---------------------------------------------------------------------------
INSERT INTO role_privilege (role_name, privilege) VALUES ('owner', 'close');

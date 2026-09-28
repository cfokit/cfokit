-- The source's own reference for a candidate, on the decision it produced (ADR-0046).
--
-- **Identity comes from the source, never from the content.** A candidate's idempotency key
-- was derived from its facts — payee, amount, account, date — so two identical coffees on one
-- statement produced one key, and the second was replayed as the first and silently lost.
-- ADR-0029 already forbade exactly that: "two five-dollar coffees on the same day are two
-- transactions". The source says which line it is; the key is derived from that.
--
-- Stored on the decision for two reasons. A replay reconstructs the candidate from this row,
-- so a candidate without its reference could not be rebuilt. And `supersedes_decision_id`
-- — present since 0012 and written by nothing — needs a way to find the earlier decision for
-- the same line once the operator has answered it: the fingerprint cannot, because it is the
-- content, and the content is what two coffees share.
--
-- Opaque text, not a foreign key. What it names belongs to whichever module produced the
-- candidate, and a REFERENCES into another module's table is the dependency ADR-0022 forbids.
--
-- NOT NULL with no default: nothing is deployed, so there is no population of decisions
-- predating it and no honest value to backfill.

ALTER TABLE assignment_decision
    ADD COLUMN candidate_source_ref text NOT NULL
        CHECK (length(trim(candidate_source_ref)) > 0);

-- "What became of this line?" — the lookup a re-run makes to find the question it answers.
CREATE INDEX assignment_decision_source_ref_idx
    ON assignment_decision (entity_id, candidate_source_ref, decided_at);

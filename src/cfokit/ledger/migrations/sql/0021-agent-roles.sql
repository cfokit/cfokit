-- The roles a person allows an agent in a company (ADR-0066 § 2).
--
-- An agent is the client a person signed in through, and acts in a company only where the person
-- has allowed it there. Allowing it chooses one of these two: `reader`, which reads, or
-- `bookkeeper`, which reads, records and posts. Neither grants, owns or acts as a principal, so an
-- agent can never widen anyone's access, its own included, and never performs an act reserved to
-- a person's own judgment (ADR-0042). An agent that creates a company holds `bookkeeper` there
-- (ADR-0066 § 5).
INSERT INTO role (name, description, never_lapses) VALUES
    ('reader', 'Reads the books, and nothing else.', false),
    ('bookkeeper', 'Reads, records and posts. Grants nothing.', false)
ON CONFLICT (name) DO NOTHING;

INSERT INTO role_privilege (role_name, privilege) VALUES
    ('reader', 'read'),
    ('bookkeeper', 'read'),
    ('bookkeeper', 'record'),
    ('bookkeeper', 'post')
ON CONFLICT DO NOTHING;

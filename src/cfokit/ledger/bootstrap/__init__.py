"""Establishing a deployment's first administrator (`IAM-06`, ADR-0038).

> "A deployment is brought into service by establishing its first deployment-scoped
> administrator, from whom every other role in it descends. This is the only privileged act
> that does not require a prior role."

Every other authority is derived. Follow the chain back — an entity grant issued by an entity
administrator, an entity's first administrator assigned when the entity was created, the entity
created by a deployment administrator — and it terminates here, at a principal nobody granted.

**The authority to perform it is possession of the database credentials**, which the operator
already holds and which no network caller can obtain by any request. That is why this is a
command rather than an endpoint: the act is unreachable from the network rather than reachable
and guarded (ADR-0038).

It therefore runs with the **owner** connection, as the migrate job does, not the application
role. That is not a convenience: the audit row for the bootstrap has no `entity_id` — there is
no entity yet — and `audit_log`'s row-level security policy, which doubles as its insert check,
admits no such row. Running as the application role would require widening that policy to accept
unscoped audit rows, which would let any session write one.

It refuses if a deployment administrator already exists, which is what makes it a bootstrap
rather than a standing backdoor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from cfokit.ledger.repository.unit_of_work import Database

__all__ = ["AlreadyBootstrapped", "Bootstrapped", "bootstrap"]


class AlreadyBootstrapped(Exception):
    """A deployment administrator already exists.

    Not a `LedgerError`: it never crosses a published interface, because no published
    interface reaches this.
    """


@dataclass(frozen=True, slots=True)
class Bootstrapped:
    principal_id: str
    grant_id: str


def bootstrap(database: Database, *, principal_id: str, operator: str) -> Bootstrapped:
    """Establish `principal_id` as the first deployment administrator.

    `operator` is who ran the command, recorded as the grantor. The act has no prior principal
    to attribute to, and recording "unknown" would be worse than recording what happened
    (`IAM-13`).

    CFOKit never issues credentials (`IAM-10`), so this names a principal the identity provider
    already knows. It does not create one, and nothing here checks that it exists — an
    identifier resolving to nobody grants nobody anything.
    """
    now = datetime.now(UTC)
    with database.deployment_write() as write:
        if write.any_deployment_administrator(now):
            raise AlreadyBootstrapped(
                "this deployment already has an administrator; grant further roles through it"
            )

        grant_id = write.grant_deployment_role(principal_id, "administrator", operator)
        write.record_audit(
            entity_id=None,
            request_id=f"bootstrap-{now.isoformat()}",
            actor=operator,
            action="bootstrap_deployment",
            subject_type="deployment_grant",
            subject_id=grant_id,
            detail={"principal": principal_id},
        )

    return Bootstrapped(principal_id=principal_id, grant_id=grant_id)

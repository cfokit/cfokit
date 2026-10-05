"""Raising a notification, answering it, reading the open ones, dismissing one (`PLT-07`).

**Raising and answering happen inside somebody else's act.** A module raises a notification in
the transaction of the act that raises it, and closes it in the transaction of the act that
answers it (ADR-0052 § 1, ADR-0056 § 1). So both take the `EntityWrite` that act already
holds, rather than opening a transaction of their own: a question that outlived a rolled-back
act, or an answer recorded for an act that never committed, is what the records rule out.

Neither writes an audit row. The act they are part of writes its own, and one state-changing
call is one row.

**Dismissing is a person's own act, and a call of its own** (ADR-0056 § 2). It is refused to a
principal acting for another, so an agent cannot dismiss a question it raised and leave it
looking resolved (`NFR-16`); it carries an idempotency key and writes its one audit row.

**Delivery is not here.** With no channel configured a notification is listed in-app and read
by the agent, which is `PLT-07` on every deployment (ADR-0052 § 2). Channels add delivery.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from cfokit.ledger.errors import (
    IdempotencyKeyRequired,
    NotAPerson,
    NotificationNotFound,
    RecipientHoldsNoRole,
)
from cfokit.ledger.repository.notifications import Notification
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorization import Capability, authorize
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.write import WriteContext

__all__ = [
    "Dismissed",
    "Notification",
    "answer",
    "dismiss",
    "notify",
    "notify_holders",
    "open_notifications",
]


@dataclass(frozen=True, slots=True)
class Dismissed:
    """What a dismissal did. `replayed` when the key was seen before; nothing was written."""

    notification_id: str
    replayed: bool = False


def notify(
    write: EntityWrite,
    *,
    recipient: str,
    notification_class: str,
    subject_ref: str,
    link: str,
) -> str:
    """Raise one notification to one recipient, inside the act that raises it.

    The recipient must hold a role in this entity, read inside the locked transaction like any
    other grant (ADR-0052 § 1). A question about these books never reaches anybody outside them.
    """
    if not write.privileges_in_force(recipient, datetime.now(UTC)):
        raise RecipientHoldsNoRole(f"{recipient} holds no role in this entity")
    return write.insert_notification(
        recipient=recipient,
        notification_class=notification_class,
        subject_ref=subject_ref,
        link=link,
    )


def notify_holders(
    write: EntityWrite,
    capability: Capability,
    *,
    notification_class: str,
    subject_ref: str,
    link: str,
) -> tuple[str, ...]:
    """Raise a notification to everyone who could answer it: each holder of `capability`.

    Returns the notifications' ids. A question two owners could each answer goes to both, and
    the first answer closes it for both (ADR-0056 § 1).
    """
    return tuple(
        notify(
            write,
            recipient=recipient,
            notification_class=notification_class,
            subject_ref=subject_ref,
            link=link,
        )
        for recipient in write.holders_of(capability.value, datetime.now(UTC))
    )


def answer(
    write: EntityWrite,
    *,
    notification_class: str,
    subject_ref: str,
    principal: Principal,
    act_ref: str,
) -> int:
    """Close every recipient's notification of this class about this subject, inside the act
    that answers it. Returns how many closed.

    The closing row names the principal whose act it was and the act, so "answered by this" is
    recorded rather than inferred. Answering a subject nobody was asked about closes nothing.
    """
    return write.answer_notifications(
        notification_class=notification_class,
        subject_ref=subject_ref,
        closed_by=principal.audit_actor,
        act_ref=act_ref,
    )


def _recipient(principal: Principal) -> str:
    """Whose notifications a caller reads: the person an agent acts for, or the caller.

    An agent reads what the person it acts for was asked, never its own list, under the
    intersection of both principals' grants (`IAM-11`, ADR-0056 § 4).
    """
    return principal.acting_for if principal.acting_for is not None else principal.id


def open_notifications(
    database: Database, *, entity_id: str, principal: Principal
) -> list[Notification]:
    """The caller's open notifications in one entity, oldest first.

    A read, so no audit row and no key; it needs a grant like any other read (`IAM-01`).
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        return write.open_notifications(_recipient(principal))


def _request_hash(*parts: object) -> str:
    """A digest of the parameters, to detect a key reused for a different request (ADR-0029).

    Duplicated from the write path rather than shared, which is the default between files that
    happen to need the same few lines.
    """
    canonical = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dismiss(database: Database, context: WriteContext, *, notification_id: str) -> Dismissed:
    """Dismiss one of the caller's own notifications, closing it for them alone.

    Refused to a principal acting for another (ADR-0042 § 2's second condition), and refused as
    not found for a notification addressed to anyone else. Dismissing one that is already closed
    — answered, or dismissed under another key — changes nothing and writes nothing.
    """
    if not context.idempotency_key:
        raise IdempotencyKeyRequired("every write requires an idempotency key")
    if context.principal.acting_for is not None:
        raise NotAPerson(
            "dismissing a notification is the recipient's own act; a delegated session may "
            "not perform it"
        )

    digest = _request_hash("dismiss_notification", notification_id)
    with database.entity_write(context.entity_id) as write:
        replay = write.claim_idempotency(context.idempotency_key, digest)
        if replay is not None:
            return Dismissed(notification_id=str(replay["notification_id"]), replayed=True)

        authorize(write, Capability.READ, context.principal)
        found = write.notification(notification_id)
        if found is None or found.recipient != context.principal.id:
            raise NotificationNotFound(f"no notification {notification_id} for this caller")

        if found.is_open:
            write.dismiss_notification(notification_id, dismissed_by=context.principal.id)
            write.record_audit(
                request_id=context.request_id,
                actor=context.principal.audit_actor,
                action="dismiss_notification",
                subject_type="notification",
                subject_id=notification_id,
                detail={"class": found.notification_class},
            )
        write.store_idempotency_result(
            context.idempotency_key, {"notification_id": notification_id}
        )

    return Dismissed(notification_id=notification_id)

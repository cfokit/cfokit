"""`python -m cfokit.ledger.bootstrap` — establish the first deployment administrator.

An explicit operator command, like migrations and for the same reason: it precedes the service
being able to serve, and it is authorised by holding the database credentials rather than by a
role (ADR-0004, ADR-0038).

    python -m cfokit.ledger.bootstrap user:geoff

Refuses if a deployment administrator already exists.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from cfokit.ledger.bootstrap import AlreadyBootstrapped, bootstrap
from cfokit.ledger.config import load_settings
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.connection import DatabaseUnavailable
from cfokit.ledger.repository.unit_of_work import Database

logger = logging.getLogger("cfokit.ledger.bootstrap")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m cfokit.ledger.bootstrap",
        description="Establish the first deployment administrator. Refuses if one exists.",
    )
    parser.add_argument(
        "principal",
        help="The principal id, as the identity provider's tokens carry it in `sub`.",
    )
    parser.add_argument(
        "--operator",
        default=os.environ.get("USER", "operator"),
        help="Who is running this. Recorded as the grantor (IAM-13).",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        settings = load_settings()
        result = bootstrap(
            Database(settings.database_url),
            principal_id=arguments.principal,
            operator=arguments.operator,
        )
    except AlreadyBootstrapped as exc:
        logger.error(json.dumps({"level": "error", "message": str(exc)}))
        return 1
    except (LedgerError, DatabaseUnavailable) as exc:
        logger.error(json.dumps({"level": "error", "message": exc.__class__.__name__}))
        return 1

    logger.info(
        json.dumps(
            {
                "level": "info",
                "message": "deployment administrator established",
                "principal": result.principal_id,
                "grant": result.grant_id,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

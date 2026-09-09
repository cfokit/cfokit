"""An archive is somebody else's file, and is bounded before it is read (`NFR-04`).

Needs no database, so it sits in the unit tier and gates every commit. The bounds themselves
live in `quickbooks.read` rather than at an adapter: the ceiling used to be on the MCP tool
alone, so `python -m cfokit.imports` had none and any endpoint added later would have inherited
none either. `read` is the one function every path onto the books goes through.

The numbers come from a real export — eight members, 979,403 bytes expanded from 904,749, an
overall ratio of 1.08 — not from a guess. That ratio is structural rather than lucky: the
members of a QuickBooks export are `.xlsx` files, which are themselves zips, so a genuine
export is very nearly incompressible and a high ratio says the file is not one.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from cfokit.imports.quickbooks import (
    MAX_ARCHIVE_BYTES,
    MAX_MEMBERS,
    MAX_UNCOMPRESSED_BYTES,
    ImportTooLarge,
    read,
)


def test_an_archive_past_the_size_ceiling_is_refused() -> None:
    with pytest.raises(ImportTooLarge):
        read(b"\0" * (MAX_ARCHIVE_BYTES + 1))


def test_an_archive_that_expands_past_the_ceiling_is_refused() -> None:
    """**The bound that matters.** A compressed size bounds an expanded size only if the ratio
    is sane. Refused from the central directory, without a byte of it being expanded — and the
    assertion below records that the size ceiling alone would have let it through."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Journal.xlsx", b"\0" * (MAX_UNCOMPRESSED_BYTES + 1))

    assert len(buffer.getvalue()) < MAX_ARCHIVE_BYTES
    with pytest.raises(ImportTooLarge):
        read(buffer.getvalue())


def test_an_archive_of_too_many_members_is_refused() -> None:
    """Thousands of tiny members cost time and file handles without tripping either size
    bound."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index in range(MAX_MEMBERS + 1):
            archive.writestr(f"member-{index}.xlsx", b"x")

    with pytest.raises(ImportTooLarge):
        read(buffer.getvalue())


def test_a_member_understating_its_size_is_refused_on_read() -> None:
    """The central directory is written by whoever made the archive, so the metadata check
    alone trusts the attacker's own arithmetic. The member read is bounded too, and that is the
    check that holds when the declared size is a lie."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Journal.xlsx", b"\0" * (MAX_UNCOMPRESSED_BYTES + 1))
    tampered = bytearray(buffer.getvalue())

    # Understate the uncompressed size in the local header and the central directory, so the
    # metadata check passes and only the bounded read can catch it.
    for signature, offset in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        at = tampered.find(signature)
        tampered[at + offset : at + offset + 4] = (1024).to_bytes(4, "little")

    with pytest.raises((ImportTooLarge, zipfile.BadZipFile)):
        read(bytes(tampered))


def test_an_export_shaped_like_a_real_one_is_inside_every_bound() -> None:
    """A bound that refuses the thing it exists to admit is a defect, not a defence. Sized from
    the real export: eight members, about a megabyte, a ratio near one."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for member in (
            "Journal.xlsx",
            "General_ledger.xlsx",
            "Trial_balance.xlsx",
            "Balance_sheet.xlsx",
            "Profit_and_loss.xlsx",
            "Customers.xlsx",
            "Vendors.xlsx",
            "Employees.xlsx",
        ):
            archive.writestr(member, b"\0" * 500_000)
    payload = buffer.getvalue()

    assert len(payload) < MAX_ARCHIVE_BYTES
    with zipfile.ZipFile(io.BytesIO(payload)) as export:
        members = export.infolist()
        assert len(members) <= MAX_MEMBERS
        assert sum(member.file_size for member in members) < MAX_UNCOMPRESSED_BYTES


def test_openpyxl_parses_through_defusedxml() -> None:
    """An `.xlsx` is a zip of XML. Without `defusedxml`, openpyxl parses it on stdlib
    ElementTree: external entities are not resolved, so this is not XXE, but billion-laughs and
    quadratic blowup are undefended. openpyxl routes through the package when it is importable
    and `OPENPYXL_DEFUSEDXML` is not set to something other than "True".

    Asserted rather than assumed: the dependency is only worth its place if it is actually in
    the path, and an environment variable can take it out of one silently.
    """
    from openpyxl.xml import DEFUSEDXML

    assert DEFUSEDXML

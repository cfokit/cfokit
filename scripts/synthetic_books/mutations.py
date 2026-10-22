"""The file cases: the accrual archive, damaged the ways real exports are before they reach us.

Each mutation is a function of the archive's bytes and nothing else, deterministic, and named by
its catalog id. The damaged files are made when a test needs them, not committed: each is a
small, reviewable change to an archive that is.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable

from synthetic_books.xlsx import archive, contents, rows

JOURNAL = "Journal.xlsx"
SHEET = "xl/worksheets/sheet1.xml"
STRINGS = "xl/sharedStrings.xml"


def _rebuild(data: bytes, member: str, change: Callable[[dict[str, bytes]], None]) -> bytes:
    """The archive with one workbook's parts changed by `change`, everything else as it was."""
    members = contents(data)
    parts = contents(members[member])
    change(parts)
    members[member] = archive(parts)
    return archive(members)


def truncated_sheet(data: bytes) -> bytes:
    """The Journal's worksheet cut off partway through a row, re-zipped as a valid archive."""

    def cut(parts: dict[str, bytes]) -> None:
        sheet = parts[SHEET]
        at = sheet.index(b"<row ", len(sheet) * 3 // 5)
        parts[SHEET] = sheet[: at + 40]

    return _rebuild(data, JOURNAL, cut)


def extra_header_row(data: bytes) -> bytes:
    """One more row above the Journal's column headings, as a customized report prints."""

    def shift(parts: dict[str, bytes]) -> None:
        sheet = parts[SHEET].decode()

        def later(match: re.Match[str]) -> str:
            number = int(match.group(2))
            return f"{match.group(1)}{number + 1 if number >= 5 else number}"

        sheet = re.sub(r'(<row r=")(\d+)', later, sheet)
        sheet = re.sub(r'(<c r="[A-Z]+)(\d+)', later, sheet)
        inserted = (
            '<row r="5"><c r="A5" t="inlineStr">'
            "<is><t>Filtered by: All accounts</t></is></c></row>"
        )
        sheet = sheet.replace('<row r="6">', inserted + '<row r="6">', 1)
        parts[SHEET] = sheet.encode()

    return _rebuild(data, JOURNAL, shift)


def invalid_utf8(data: bytes) -> bytes:
    """The first é in the Journal's strings made into a byte sequence UTF-8 does not allow."""

    def damage(parts: dict[str, bytes]) -> None:
        parts[STRINGS] = parts[STRINGS].replace("é".encode(), b"\xc3\x28", 1)

    return _rebuild(data, JOURNAL, damage)


def macos_rezip(data: bytes) -> bytes:
    """Unzipped and zipped again on a Mac: AppleDouble entries under __MACOSX/ for each file."""
    members = contents(data)
    apple_double = b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        " + bytes(64)
    for name in list(members):
        members[f"__MACOSX/._{name}"] = apple_double
    members[".DS_Store"] = b"\x00\x00\x00\x01Bud1" + bytes(32)
    return archive(members)


def nested_folder(data: bytes) -> bytes:
    """Zipped as a folder: every report under export/ rather than at the root."""
    return archive({f"export/{name}": body for name, body in contents(data).items()})


def excel_resave(data: bytes) -> bytes:
    """Every workbook as Excel saves it: a formula's result cached beside it, numbers without
    trailing zeros, and the styles and document properties Excel always writes."""
    members = contents(data)
    for name, body in members.items():
        parts = contents(body)
        sheet = parts[SHEET].decode()
        sheet = re.sub(r"<f>([^<]*)</f>", r"<f>\1</f><v>\1</v>", sheet)
        sheet = re.sub(r"<v>(-?\d+)\.(\d*?)0*</v>", _trimmed, sheet)
        parts[SHEET] = sheet.encode()
        parts["xl/styles.xml"] = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>'
            b"</styleSheet>"
        )
        parts["docProps/app.xml"] = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b"<Properties><Application>Microsoft Excel</Application></Properties>"
        )
        members[name] = archive(parts)
    return archive(members)


def _trimmed(match: re.Match[str]) -> str:
    whole, fraction = match.group(1), match.group(2)
    return f"<v>{whole}.{fraction}</v>" if fraction else f"<v>{whole}</v>"


def single_workbook(data: bytes) -> bytes:
    """Journal.xlsx chosen on its own, rather than the archive it came in."""
    return contents(data)[JOURNAL]


def csv_instead(data: bytes) -> bytes:
    """The journal as the report screen exports it to CSV, rather than through Export Data."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    for row in rows(contents(data)[JOURNAL]):
        writer.writerow(["" if cell is None else cell for cell in row])
    return "﻿".encode() + out.getvalue().encode()


MUTATIONS: dict[str, Callable[[bytes], bytes]] = {
    "f-truncated-sheet": truncated_sheet,
    "f-extra-header-row": extra_header_row,
    "f-invalid-utf8": invalid_utf8,
    "f-macos-rezip": macos_rezip,
    "f-nested-folder": nested_folder,
    "f-excel-resave": excel_resave,
    "f-single-workbook": single_workbook,
    "f-csv-instead": csv_instead,
}

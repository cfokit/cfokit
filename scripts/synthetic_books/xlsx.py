"""A workbook of one worksheet, written the way QuickBooks writes its exports.

Strings go into a shared table; a figure is a number cell or, in a statement, a formula with no
cached result; a row holding nothing is left out of the XML. This is the shape the reader in
`web/src/quickbooks/` was built against, and the shape `web/src/quickbooks/synthetic.ts` writes.

The archive's bytes are not stable across zlib builds, so nothing should compare them: compare
the members' contents, which are.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from xml.etree import ElementTree
from xml.sax.saxutils import escape


@dataclass(frozen=True, slots=True)
class Number:
    """A number cell, holding exactly these digits."""

    value: Decimal


@dataclass(frozen=True, slots=True)
class Formula:
    """A formula cell with no cached result, as QuickBooks writes a statement's figures."""

    value: Decimal


type Cell = str | Number | Formula | None
type Row = list[Cell]

# Every member of every archive carries this time, so writing twice writes the same archive.
FIXED_TIME = (2026, 7, 1, 9, 0, 0)

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"


def column(index: int) -> str:
    name = ""
    at = index + 1
    while at > 0:
        at, rest = divmod(at - 1, 26)
        name = chr(65 + rest) + name
    return name


def digits(value: Decimal) -> str:
    return format(value, "f")


def sheet_xml(rows: list[Row]) -> tuple[str, list[str]]:
    strings: list[str] = []
    index: dict[str, int] = {}
    body: list[str] = []
    for r, row in enumerate(rows, 1):
        cells: list[str] = []
        for c, cell in enumerate(row):
            ref = f"{column(c)}{r}"
            match cell:
                case None:
                    continue
                case Number(value=value):
                    cells.append(f'<c r="{ref}"><v>{digits(value)}</v></c>')
                case Formula(value=value):
                    cells.append(f'<c r="{ref}"><f>{digits(value)}</f></c>')
                case str():
                    if cell not in index:
                        index[cell] = len(strings)
                        strings.append(cell)
                    cells.append(f'<c r="{ref}" t="s"><v>{index[cell]}</v></c>')
        if cells:
            body.append(f'<row r="{r}">{"".join(cells)}</row>')
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN}"><sheetData>{"".join(body)}</sheetData></worksheet>'
    )
    return xml, strings


def workbook(rows: list[Row]) -> bytes:
    sheet, strings = sheet_xml(rows)
    shared = "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in strings)
    members = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{PACKAGE}"><Relationship Id="rId1" '
            f'Type="{RELATIONSHIPS}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<workbook xmlns="{MAIN}" xmlns:r="{RELATIONSHIPS}"><sheets>'
            '<sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{PACKAGE}">'
            f'<Relationship Id="rId1" Type="{RELATIONSHIPS}/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{RELATIONSHIPS}/sharedStrings" '
            'Target="sharedStrings.xml"/></Relationships>'
        ),
        "xl/sharedStrings.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<sst xmlns="{MAIN}" count="{len(strings)}" uniqueCount="{len(strings)}">'
            f"{shared}</sst>"
        ),
        "xl/worksheets/sheet1.xml": sheet,
    }
    return archive({name: text.encode() for name, text in members.items()})


def archive(members: dict[str, bytes]) -> bytes:
    """A deflated zip of these members, in this order, each stamped with `FIXED_TIME`."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(info, data)
    return buffer.getvalue()


def contents(data: bytes) -> dict[str, bytes]:
    """Every member of an archive, uncompressed: what two archives are compared by."""
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        return {name: source.read(name) for name in source.namelist()}


def rows(data: bytes) -> list[list[str | None]]:
    """A workbook's first worksheet as text: a string as itself, a number's digits, a formula's
    body. Reads ours and QuickBooks' alike; refuses a document type declaration, as the reader
    in `web/` does, because that is the only way an XML part can expand.
    """
    parts = contents(data)

    def parse(name: str) -> ElementTree.Element:
        text = parts[name]
        if b"<!DOCTYPE" in text[:4096].upper():
            raise ValueError(f"{name} declares a document type")
        return ElementTree.fromstring(text)  # noqa: S314 — a DTD, the one way to expand, is refused

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def text_of(element: ElementTree.Element) -> str:
        return "".join(t.text or "" for t in element.iter() if local(t.tag) == "t")

    strings = []
    if "xl/sharedStrings.xml" in parts:
        strings = [text_of(si) for si in parse("xl/sharedStrings.xml") if local(si.tag) == "si"]
    out: list[list[str | None]] = []
    for row in parse("xl/worksheets/sheet1.xml").iter():
        if local(row.tag) != "row":
            continue
        while len(out) < int(row.get("r", len(out) + 1)) - 1:
            out.append([])
        cells: dict[int, str] = {}
        for cell in row:
            if local(cell.tag) != "c":
                continue
            at = 0
            for letter in re.match(r"[A-Z]+", cell.get("r", "A")).group():  # type: ignore[union-attr]
                at = at * 26 + ord(letter) - 64
            children = {local(child.tag): child for child in cell}
            if "f" in children:
                cells[at - 1] = children["f"].text or ""
            elif cell.get("t") == "inlineStr" and "is" in children:
                cells[at - 1] = text_of(children["is"])
            elif "v" in children and children["v"].text is not None:
                value = children["v"].text
                cells[at - 1] = strings[int(value)] if cell.get("t") == "s" else value
        out.append([cells.get(i) for i in range(max(cells, default=-1) + 1)])
    return out

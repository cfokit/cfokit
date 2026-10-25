"""A workbook of one worksheet, written the way QuickBooks writes its exports.

Strings go into a shared table; a figure is a number cell or, in a statement or a trial balance,
a formula; a row holding nothing is left out of the XML. QuickBooks writes each formula with a
cached result of zero, which a spreadsheet recalculates and a reader must not take for the
figure. This is the shape of an Export Data download, compared cell by cell (ADR-0078).

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
    """A formula cell: a figure written as a formula, or a sum of cells above, such as
    `(B9)+(B10)`. Its cached result is zero, as QuickBooks writes it."""

    text: str

    @classmethod
    def of(cls, value: Decimal) -> Formula:
        """A figure as QuickBooks writes it in a formula: to the cent, and a zero unsigned."""
        return cls(digits((value + 0).quantize(Decimal("0.01"))))


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
                case Formula(text=text):
                    cells.append(f'<c r="{ref}"><f>{escape(text)}</f><v>0</v></c>')
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
    body. Reads ours and QuickBooks' alike."""
    return [[None if cell is None else cell[1] for cell in row] for row in cells(data)]


def cells(data: bytes) -> list[list[tuple[str, str] | None]]:
    """A workbook's first worksheet as typed cells: `("s", text)` for a string, `("n", digits)`
    for a number, `("f", body)` for a formula, whatever it caches. Refuses a document type
    declaration, as the reader in `web/` does, because that is the only way an XML part can
    expand.
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
    out: list[list[tuple[str, str] | None]] = []
    for row in parse("xl/worksheets/sheet1.xml").iter():
        if local(row.tag) != "row":
            continue
        while len(out) < int(row.get("r", len(out) + 1)) - 1:
            out.append([])
        found: dict[int, tuple[str, str]] = {}
        for cell in row:
            if local(cell.tag) != "c":
                continue
            at = 0
            for letter in re.match(r"[A-Z]+", cell.get("r", "A")).group():  # type: ignore[union-attr]
                at = at * 26 + ord(letter) - 64
            children = {local(child.tag): child for child in cell}
            if "f" in children:
                found[at - 1] = ("f", children["f"].text or "")
            elif cell.get("t") == "inlineStr" and "is" in children:
                found[at - 1] = ("s", text_of(children["is"]))
            elif "v" in children and children["v"].text is not None:
                value = children["v"].text
                found[at - 1] = (
                    ("s", strings[int(value)]) if cell.get("t") == "s" else ("n", value)
                )
        out.append([found.get(i) for i in range(max(found, default=-1) + 1)])
    return out


def values(data: bytes) -> list[list[str | None]]:
    """A worksheet as its figures: as `rows`, but each formula worked out, as a spreadsheet
    would. QuickBooks' formulas are a number, or sums and differences of cells and bracketed
    terms, such as `((B11)+(B14))+(B18)` or `(B9)-(B16)`."""
    grid = cells(data)
    worked: dict[tuple[int, int], Decimal] = {}

    def figure(row: int, col: int) -> Decimal:
        cell = grid[row][col] if row < len(grid) and col < len(grid[row]) else None
        if cell is None or cell[0] == "s":
            return Decimal(0)
        if (row, col) not in worked:
            worked[row, col] = evaluate(cell[1]) if cell[0] == "f" else Decimal(cell[1])
        return worked[row, col]

    def evaluate(text: str) -> Decimal:
        parts = re.findall(r"[A-Z]+\d+|\d+(?:\.\d+)?|[()+-]", text)
        if "".join(parts) != text.replace(" ", ""):
            raise ValueError(f"a formula this does not read: {text}")
        at = 0

        def term() -> Decimal:
            nonlocal at
            part = parts[at]
            at += 1
            if part == "-":
                return -term()
            if part == "(":
                inner = expression()
                at += 1  # the closing bracket
                return inner
            if part[0].isalpha():
                letters = re.match(r"[A-Z]+", part).group()  # type: ignore[union-attr]
                col = 0
                for letter in letters:
                    col = col * 26 + ord(letter) - 64
                return figure(int(part[len(letters) :]) - 1, col - 1)
            return Decimal(part)

        def expression() -> Decimal:
            nonlocal at
            total = term()
            while at < len(parts) and parts[at] in "+-":
                sign = parts[at]
                at += 1
                total = total + term() if sign == "+" else total - term()
            return total

        return expression()

    return [
        [
            None if cell is None else format(figure(r, c), "f") if cell[0] == "f" else cell[1]
            for c, cell in enumerate(row)
        ]
        for r, row in enumerate(grid)
    ]

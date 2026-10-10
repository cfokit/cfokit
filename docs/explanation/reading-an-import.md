# Reading an import

When an import finishes, CFOKit compares the books it now holds with what QuickBooks said, and
the import page shows the result. These are the differences you may see, and what each means.

**A cash-basis difference is expected.** QuickBooks' reports are often run on the cash basis.
CFOKit records every invoice and bill when it happens, so receivables, and the income not yet
recognized against them, differ by exactly what is unsettled. The import page marks this as
expected. To compare like with like, set QuickBooks' accounting method to Accrual and export
again.

**Importing the same file again is safe.** Each transaction's key comes from the file and its
row, so an import that stopped partway resumes, and nothing is counted twice. A new export from
QuickBooks is a different file, and so a second import: use a fresh company for one.

**Rows left out were refused before anything was posted.** A transaction with one line moves no
value, and one whose debits and credits differ cannot balance. The page names each one, with the
row it came from.

Later, Claude can answer whether the books still match QuickBooks. It reads the same comparison
through the `import_reconciliations` tool.

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import {
  ActionBar,
  AppFrame,
  Button,
  Card,
  Dialog,
  DropZone,
  Money,
  MoneyTable,
  Notice,
  Progress,
  StepIndicator,
  TextField,
  TextLink,
} from ".";
import { accepts } from "./DropZone";

// Each expectation is a behavior the design system's README or ADR-0049 states for the
// component; the README sentence is quoted where it is the source.

describe("Money", () => {
  test("a negative shows in parentheses and is read as minus, never by color alone", () => {
    const { container } = render(<Money amount="-1250.5000000000" />);
    expect(container.textContent).toBe("(minus 1,250.50)");
    expect(container.querySelector(".sr-only")?.textContent).toBe("minus ");
    expect(container.innerHTML).not.toMatch(/danger|red/);
  });

  test("set in tabular figures", () => {
    const { container } = render(<Money amount="100.00" />);
    expect(container.firstElementChild?.className).toContain("tabular-nums");
  });
});

describe("Button", () => {
  test("is a button that does not submit unless asked", () => {
    render(<Button variant="primary">Import</Button>);
    expect(screen.getByRole("button", { name: "Import" }).getAttribute("type")).toBe("button");
  });

  test("is at least target-min tall", () => {
    render(<Button>Cancel</Button>);
    expect(screen.getByRole("button").className).toContain("min-h-target-min");
  });

  test('"Destructive: danger text on surface, never a filled red"', () => {
    render(<Button variant="destructive">Delete</Button>);
    const className = screen.getByRole("button").className;
    expect(className).toContain("text-danger");
    expect(className).not.toContain("bg-danger");
  });
});

describe("TextField", () => {
  test("its label, help and error belong to the input", () => {
    render(
      <TextField
        label="Fiscal year end"
        help="The last day of your accounting year."
        error="Choose a date."
      />,
    );
    const input = screen.getByLabelText("Fiscal year end");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const described = (input.getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent);
    expect(described).toEqual(["The last day of your accounting year.", "Choose a date."]);
  });

  test('"An error puts danger on the border and a sentence below, not a color alone"', () => {
    render(<TextField label="Company name" error="Enter the company's name." />);
    expect(screen.getByLabelText("Company name").className).toContain("border-danger");
    expect(screen.getByText("Enter the company's name.")).toBeTruthy();
  });

  test("typed text is input size, so iOS Safari does not zoom", () => {
    render(<TextField label="Amount" inputMode="decimal" />);
    const input = screen.getByLabelText("Amount");
    expect(input.className).toContain("text-input");
    expect(input.getAttribute("inputmode")).toBe("decimal");
  });
});

describe("Notice", () => {
  test("the leading word carries the state, so nothing depends on color", () => {
    render(
      <Notice tone="danger" label="Refused">
        This file isn&apos;t a QuickBooks export.
      </Notice>,
    );
    const label = screen.getByText("Refused");
    expect(label.className).toContain("text-danger");
    expect(label.parentElement?.className).toContain("border-danger");
  });

  test("a notice that is part of the page is read in place, not announced", () => {
    render(
      <Notice tone="neutral" label="Safe to leave">
        You can close this page.
      </Notice>,
    );
    expect(screen.queryByRole("status")).toBeNull();
  });

  test("an announced notice is a live region on the page before its text arrives", async () => {
    // Screen readers announce changes inside a live region, not a region arriving with its text.
    render(
      <Notice tone="danger" label="Refused" announce>
        This file isn&apos;t a QuickBooks export.
      </Notice>,
    );
    const region = screen.getByRole("status");
    expect(region.textContent).toBe("");
    await waitFor(() => expect(region.textContent).toContain("Refused"));
  });
});

describe("Card", () => {
  test("titles its section", () => {
    render(<Card title="What will be imported">Details</Card>);
    expect(screen.getByRole("heading", { name: "What will be imported" })).toBeTruthy();
  });
});

describe("TextLink", () => {
  test("is a link to where it goes", () => {
    render(<TextLink href="/register">Create an account</TextLink>);
    expect(screen.getByRole("link", { name: "Create an account" }).getAttribute("href")).toBe(
      "/register",
    );
  });
});

describe("Progress", () => {
  test('"the count beside it ... (2,000 of 5,556)"', () => {
    render(<Progress value={2000} max={5556} unit="transactions" label="Import progress" />);
    const bar = screen.getByRole("progressbar", { name: "Import progress" });
    expect(bar.getAttribute("aria-valuenow")).toBe("2000");
    expect(bar.getAttribute("aria-valuetext")).toBe("2,000 of 5,556 transactions");
    expect(screen.getByText("2,000 of 5,556 transactions")).toBeTruthy();
  });
});

describe("StepIndicator", () => {
  const steps = ["Create your company", "Import your books", "Compare with QuickBooks"];

  test("marks the current step, and the ones before it as done", () => {
    render(<StepIndicator steps={steps} current={1} label="Setup steps" />);
    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items[1]?.getAttribute("aria-current")).toBe("step");
    expect(items[0]?.textContent).toContain("(done)");
    expect(items[2]?.textContent).not.toContain("(done)");
  });

  test("says where the person is in one line on a phone", () => {
    render(<StepIndicator steps={steps} current={1} label="Setup steps" />);
    expect(screen.getByText("Step 2 of 3: Import your books")).toBeTruthy();
  });
});

describe("DropZone", () => {
  const zip = new File(["zip"], "export.zip", { type: "application/zip" });
  const pdf = new File(["pdf"], "statement.pdf", { type: "application/pdf" });

  function setup() {
    const onFile = vi.fn();
    const onReject = vi.fn();
    const { container } = render(
      <DropZone prompt="Drop the export here." accept=".zip" onFile={onFile} onReject={onReject} />,
    );
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    if (input === null) throw new Error("no file input");
    return { onFile, onReject, input, zone: container.firstElementChild as HTMLElement };
  }

  test('"Choose file" opens the picker, and a chosen file is handed over', () => {
    const { onFile, input } = setup();
    const click = vi.spyOn(input, "click");
    fireEvent.click(screen.getByRole("button", { name: "Choose file" }));
    expect(click).toHaveBeenCalled();
    fireEvent.change(input, { target: { files: [zip] } });
    expect(onFile).toHaveBeenCalledWith(zip);
  });

  test("dropping a file is a shortcut beside the button", () => {
    const { onFile, zone } = setup();
    fireEvent.dragOver(zone, { dataTransfer: { files: [zip] } });
    expect(zone.className).toContain("border-accent");
    fireEvent.drop(zone, { dataTransfer: { files: [zip] } });
    expect(onFile).toHaveBeenCalledWith(zip);
    expect(zone.className).not.toContain("border-accent");
  });

  test("a file accept does not allow is refused, dropped or chosen", () => {
    const { onFile, onReject, input, zone } = setup();
    fireEvent.drop(zone, { dataTransfer: { files: [pdf] } });
    fireEvent.change(input, { target: { files: [pdf] } });
    expect(onReject).toHaveBeenCalledTimes(2);
    expect(onFile).not.toHaveBeenCalled();
  });

  test.each([
    [".zip", "export.zip", "application/zip", true],
    [".zip", "EXPORT.ZIP", "", true],
    [".zip", "export.zip.pdf", "application/pdf", false],
    ["application/zip", "export", "application/zip", true],
    ["image/*", "logo.png", "image/png", true],
    ["image/*", "notes.txt", "text/plain", false],
    [".csv, .zip", "export.zip", "", true],
    [undefined, "anything.bin", "", true],
  ])("accept %s takes %s (%s): %s", (accept, name, type, expected) => {
    expect(accepts(accept, new File([""], name, { type }))).toBe(expected);
  });
});

describe("MoneyTable", () => {
  const columns = [
    { key: "account", header: "Account", kind: "text" as const },
    { key: "ours", header: "CFOKit", kind: "money" as const },
    { key: "theirs", header: "QuickBooks", kind: "money" as const },
  ];
  const rows = [
    { id: "1", cells: { account: "Checking", ours: "1200.00", theirs: "1200.00" } },
    { id: "2", cells: { account: "Undeposited Funds", ours: "-50", theirs: "0" }, flagged: true },
  ];

  test("the currency is shown once, in the money columns' headers", () => {
    render(<MoneyTable caption="Balances" columns={columns} rows={rows} currency="USD" />);
    const table = screen.getByRole("table", { name: "Balances" });
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual(["Account", "CFOKit USD", "QuickBooks USD"]);
    expect(within(table).getAllByRole("cell")[0]?.textContent).toBe("1,200.00)");
  });

  test("the totals are the API's, shown as given, not summed on the page (RPT-12)", () => {
    // Deliberately not the sum of the rows: the page must show what it is given.
    render(
      <MoneyTable
        caption="Balances"
        columns={columns}
        rows={rows}
        currency="USD"
        totals={{ ours: "1150.004", theirs: "999.995" }}
      />,
    );
    const table = screen.getByRole("table", { name: "Balances" });
    const foot = table.querySelector("tfoot");
    expect(foot?.textContent).toContain("1,150.00");
    expect(foot?.textContent).toContain("1,000.00");
  });

  test("a flagged row is marked, and the mark is announced", () => {
    render(<MoneyTable caption="Balances" columns={columns} rows={rows} currency="USD" />);
    const table = screen.getByRole("table", { name: "Balances" });
    expect(within(table).getByText("Look at this:", { exact: false })).toBeTruthy();
  });

  test("two figures a row become a labeled list below bp-tablet", () => {
    render(<MoneyTable caption="Balances" columns={columns} rows={rows} currency="USD" />);
    const list = screen.getByRole("list", { name: "Balances" });
    expect(list.className).toContain("tablet:hidden");
    expect(within(list).getAllByText("QuickBooks USD")).toHaveLength(2);
  });

  test("a row with no figure for a column shows an empty cell, not a zero", () => {
    const partial = [{ id: "1", cells: { account: "Checking", ours: "10.00" } }];
    render(<MoneyTable caption="Balances" columns={columns} rows={partial} currency="USD" />);
    const cells = within(screen.getByRole("table")).getAllByRole("cell");
    expect(cells[1]?.textContent).toBe("");
  });

  test("a wider table keeps its columns and scrolls in its own frame", () => {
    const wide = [...columns, { key: "difference", header: "Difference", kind: "money" as const }];
    render(<MoneyTable caption="Balances" columns={wide} rows={rows} currency="USD" />);
    expect(screen.queryByRole("list")).toBeNull();
    const frame = screen.getByRole("table").parentElement;
    expect(frame?.className).toContain("overflow-x-auto");
    expect(frame?.className).not.toContain("hidden");
  });
});

describe("Dialog", () => {
  function Harness({ onClose }: { onClose: () => void }) {
    const [open, setOpen] = useState(true);
    return (
      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          onClose();
        }}
        title="Stop the import?"
        actions={<Button onClick={() => setOpen(false)}>Keep importing</Button>}
      >
        The transactions imported so far stay.
      </Dialog>
    );
  }

  test("opens as a modal named by its title, and reports when it closes", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const dialog = screen.getByRole("dialog", { name: "Stop the import?" });
    expect((dialog as HTMLDialogElement).open).toBe(true);
    act(() => screen.getByRole("button", { name: "Keep importing" }).click());
    expect((dialog as HTMLDialogElement).open).toBe(false);
    expect(onClose).toHaveBeenCalled();
  });
});

describe("AppFrame", () => {
  test("names the company, and signs out from the header or, on a phone, its menu", () => {
    const onSignOut = vi.fn();
    render(
      <AppFrame company="Hollis Varga Consulting LLC" person="Dana Whitfield" onSignOut={onSignOut}>
        <h1>Import your books</h1>
      </AppFrame>,
    );
    expect(screen.getByText("Hollis Varga Consulting LLC")).toBeTruthy();
    expect(screen.getByRole("img", { name: "CFOKit" })).toBeTruthy();
    expect(screen.getByRole("main").textContent).toBe("Import your books");

    const menu = screen.getByRole("button", { name: "Account" });
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(menu);
    expect(menu.getAttribute("aria-expanded")).toBe("true");
    const panel = document.getElementById(menu.getAttribute("aria-controls") ?? "");
    expect(panel?.textContent).toContain("Dana Whitfield");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(menu.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(screen.getAllByRole("button", { name: "Sign out" })[0] as HTMLElement);
    expect(onSignOut).toHaveBeenCalled();
  });
});

describe("ActionBar", () => {
  test("pins to the bottom on a phone and sits inline from bp-tablet", () => {
    render(
      <ActionBar>
        <Button variant="primary" fullWidth>
          Import
        </Button>
      </ActionBar>,
    );
    const bar = screen.getByRole("button", { name: "Import" }).parentElement;
    expect(bar?.className).toContain("fixed");
    expect(bar?.className).toContain("tablet:static");
  });

  test("keeps clear as much of the page's end as the bar is tall", () => {
    // jsdom does no layout; the bar reports the height two stacked buttons give it on a phone.
    const height = vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(124);
    render(
      <ActionBar>
        <Button fullWidth>Import</Button>
        <Button fullWidth>Cancel</Button>
      </ActionBar>,
    );
    const bar = screen.getByRole("button", { name: "Import" }).parentElement;
    expect((bar?.nextElementSibling as HTMLElement).style.height).toBe("124px");
    height.mockRestore();
  });
});

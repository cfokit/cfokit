import { useState, type ReactNode } from "react";
import {
  ActionBar,
  AppFrame,
  Button,
  Card,
  CopyBlock,
  Dialog,
  DropZone,
  Money,
  MoneyTable,
  Notice,
  Progress,
  StepIndicator,
  TextField,
  TextLink,
} from "../components";

// Every component in its states, for looking at in a browser (`pnpm dev`, then /app/gallery.html)
// and for the accessibility test. Not part of the build. Its copy follows the design system's
// README; the figures are placeholders, not anyone's books.

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-display text-heading-compact text-ink tablet:text-heading">{title}</h2>
      {children}
    </section>
  );
}

const steps = [
  "Create your company",
  "Import your books",
  "Compare with QuickBooks",
  "Back to Claude",
];

export function Gallery() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [file, setFile] = useState<string>();
  const [refused, setRefused] = useState<string>();

  return (
    <AppFrame company="[COMPANY NAME]" person="[PERSON NAME]" onSignOut={() => undefined}>
      <div className="flex flex-col gap-10">
        <h1 className="font-display text-display-compact text-ink tablet:text-display">
          Components
        </h1>

        <Section title="Step indicator">
          <StepIndicator steps={steps} current={1} label="Setup steps" />
        </Section>

        <Section title="Buttons">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">Import</Button>
            <Button>Try another file</Button>
            <Button variant="destructive">Stop the import</Button>
            <Button variant="link">Sign out</Button>
            <Button variant="primary" disabled>
              Create company
            </Button>
          </div>
        </Section>

        <Section title="Links">
          <TextLink href="#">Create an account</TextLink>
        </Section>

        <Section title="Text fields">
          <Card title="Your company">
            <div className="flex max-w-reading-max flex-col gap-6">
              <TextField
                label="Company name"
                autoComplete="organization"
                placeholder="[COMPANY NAME]"
              />
              <TextField
                label="Accounting basis"
                help="Accrual: income counts when you invoice, not when you're paid."
                defaultValue="Accrual"
              />
              <TextField
                label="Opening balance"
                inputMode="decimal"
                defaultValue="12,50.00"
                error="This isn't an amount. Enter it as 1250.00."
              />
            </div>
          </Card>
        </Section>

        <Section title="Drop zone">
          <DropZone
            prompt="Drop the QuickBooks export here, or choose it from your computer."
            accept=".zip"
            onFile={(f) => {
              setRefused(undefined);
              setFile(f.name);
            }}
            onReject={(f) => {
              setFile(undefined);
              setRefused(f.name);
            }}
          />
          {file !== undefined && <p className="text-body text-ink">Chosen: {file}</p>}
          {refused !== undefined && (
            <Notice key={refused} tone="danger" label="Refused" announce>
              {refused} isn&apos;t a QuickBooks export. Choose the .zip QuickBooks gave you.
            </Notice>
          )}
        </Section>

        <Section title="Progress">
          <Progress value={2140} max={5553} unit="transactions" label="Import progress" />
        </Section>

        <Section title="Notices">
          <Notice tone="success" label="Matches">
            25 of 27 accounts match QuickBooks exactly.
          </Notice>
          <Notice tone="warning" label="Expected difference">
            QuickBooks reports on cash basis and you chose accrual, so balances that depend on the
            basis differ.
          </Notice>
          <Notice tone="danger" label="Refused">
            This file isn&apos;t a QuickBooks export. Choose the .zip QuickBooks gave you, or export
            your books again.
          </Notice>
          <Notice tone="neutral" label="Safe to leave">
            You can close this page. Choose the same file again and the import picks up where it
            stopped.
          </Notice>
        </Section>

        <Section title="Copy block">
          <CopyBlock
            label="Your first question"
            text={
              "My books are imported into CFOKit. Confirm they match QuickBooks and explain any differences, then summarize this year's profit and loss and my cash position."
            }
          />
        </Section>

        <Section title="Money">
          <p className="flex flex-wrap items-baseline gap-6 text-ink">
            <Money amount="1250.00" />
            <Money amount="-1250.00" />
            <Money amount="25469.00" variant="total" />
          </p>
        </Section>

        <Section title="Money table">
          <MoneyTable
            caption="Balances compared with QuickBooks"
            currency="USD"
            columns={[
              { key: "account", header: "Account", kind: "text" },
              { key: "ours", header: "CFOKit", kind: "money" },
              { key: "theirs", header: "QuickBooks", kind: "money" },
            ]}
            rows={[
              {
                id: "a",
                cells: { account: "[ACCOUNT NAME]", ours: "12000.00", theirs: "12000.00" },
              },
              {
                id: "b",
                cells: { account: "[ACCOUNT NAME]", ours: "-1250.00", theirs: "-1000.00" },
                flagged: true,
              },
              { id: "c", cells: { account: "[ACCOUNT NAME]", ours: "412.50", theirs: "412.50" } },
            ]}
            totals={{ ours: "11162.50", theirs: "11412.50" }}
          />
          <MoneyTable
            caption="Balances with their differences"
            currency="USD"
            columns={[
              { key: "account", header: "Account", kind: "text" },
              { key: "ours", header: "CFOKit", kind: "money" },
              { key: "theirs", header: "QuickBooks", kind: "money" },
              { key: "difference", header: "Difference", kind: "money" },
            ]}
            rows={[
              {
                id: "b",
                cells: {
                  account: "[ACCOUNT NAME]",
                  ours: "-1250.00",
                  theirs: "-1000.00",
                  difference: "-250.00",
                },
                flagged: true,
              },
            ]}
          />
        </Section>

        <Section title="Dialog">
          <div>
            <Button onClick={() => setDialogOpen(true)}>Stop the import</Button>
          </div>
          <Dialog
            open={dialogOpen}
            onClose={() => setDialogOpen(false)}
            title="Stop the import?"
            actions={
              <>
                <Button onClick={() => setDialogOpen(false)}>Keep importing</Button>
                <Button variant="destructive" onClick={() => setDialogOpen(false)}>
                  Stop the import
                </Button>
              </>
            }
          >
            The transactions imported so far stay. Choose the same file again to finish.
          </Dialog>
        </Section>

        <Section title="Action bar">
          <ActionBar>
            <Button variant="primary" fullWidth className="tablet:w-auto">
              Import
            </Button>
            <Button fullWidth className="tablet:w-auto">
              Cancel
            </Button>
          </ActionBar>
        </Section>
      </div>
    </AppFrame>
  );
}

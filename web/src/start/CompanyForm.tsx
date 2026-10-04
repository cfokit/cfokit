import { useState, type FormEvent } from "react";
import { ApiError, useApi } from "../api";
import { ActionBar, Button, Notice, TextField } from "../components";
import type { Basis, Company } from "../quickbooks/read";

/** What `POST /entities` takes. Every declaration is required and none has a default. */
export interface NewCompany {
  slug: string;
  name: string;
  accounting_basis: "accrual" | "cash";
  fiscal_year_end_month: number;
  fiscal_year_end_day: number;
  functional_currency: string;
  time_zone: string;
}

const BASES: { value: "accrual" | "cash"; label: string; explained: string }[] = [
  {
    value: "accrual",
    label: "Accrual",
    explained: "Income counts when you invoice, and expenses when you're billed.",
  },
  {
    value: "cash",
    label: "Cash",
    explained: "Income counts when you're paid, and expenses when you pay.",
  },
];

const DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

function isTimeZone(zone: string): boolean {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: zone });
    return zone.trim() !== "";
  } catch {
    return false;
  }
}

/** A stable identifier for the company, unique in this deployment: its name, and a few random letters. */
function slugFor(name: string): string {
  const base = name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  const suffix = [...crypto.getRandomValues(new Uint8Array(3))]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return `${base || "company"}-${suffix}`;
}

interface CompanyFormProps {
  /** What the export says about the company. */
  stated: Company;
  /** The currency the export's figures are in. */
  currency: string;
  onCreated: (entityId: string, name: string) => void;
  onBack: () => void;
}

/**
 * The company the books will be kept for, from what the export states: its name and the basis its
 * reports were run on. The person confirms those and adds what the export does not state — the
 * fiscal year end and the time zone (ADR-0058 § 1).
 */
export function CompanyForm({ stated, currency, onCreated, onBack }: CompanyFormProps) {
  const api = useApi();
  const [name, setName] = useState(stated.name);
  const [basis, setBasis] = useState<Basis>(stated.basis);
  const [month, setMonth] = useState("12");
  const [day, setDay] = useState("31");
  const [zone, setZone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [checked, setChecked] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const monthNumber = Number(month);
  const dayNumber = Number(day);
  const errors = {
    name: name.trim() === "" ? "Enter the company's name." : undefined,
    basis: basis === "unknown" ? "Choose the basis the company keeps its books on." : undefined,
    month:
      Number.isInteger(monthNumber) && monthNumber >= 1 && monthNumber <= 12
        ? undefined
        : "Enter a month from 1 to 12.",
    day:
      Number.isInteger(dayNumber) &&
      dayNumber >= 1 &&
      dayNumber <= (DAYS_IN_MONTH[monthNumber - 1] ?? 31)
        ? undefined
        : "Enter a day that month has.",
    zone: isTimeZone(zone) ? undefined : "Enter a time zone such as America/New_York.",
  };
  const valid = Object.values(errors).every((error) => error === undefined);
  // An error appears once the person has tried to submit, not while they are still typing.
  const shown = (error: string | undefined) => (checked && error !== undefined ? { error } : {});

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setChecked(true);
    if (!valid || basis === "unknown") return;
    setSaving(true);
    setFailure(null);
    const company: NewCompany = {
      slug: slugFor(name),
      name: name.trim(),
      accounting_basis: basis,
      fiscal_year_end_month: monthNumber,
      fiscal_year_end_day: dayNumber,
      functional_currency: currency,
      time_zone: zone.trim(),
    };
    try {
      const created = await api.post<{ entity_id: string }>("/entities", company);
      onCreated(created.entity_id, company.name);
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : "CFOKit isn't answering.");
      setSaving(false);
    }
  };

  return (
    <form className="flex flex-col gap-6" onSubmit={(event) => void submit(event)} noValidate>
      <p className="text-body text-ink">
        From your export. Check it, and add what QuickBooks doesn&apos;t say. These can&apos;t be
        changed later: every report is computed against them.
      </p>
      <TextField
        label="Company name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        {...shown(errors.name)}
        autoComplete="organization"
      />
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-label text-ink">Accounting basis</legend>
        <div className="flex flex-wrap gap-3">
          {BASES.map((option) => (
            <Button
              key={option.value}
              variant={basis === option.value ? "primary" : "secondary"}
              aria-pressed={basis === option.value}
              onClick={() => setBasis(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
        <ul className="flex flex-col gap-1 text-caption text-ink-muted">
          {BASES.map((option) => (
            <li key={option.value}>
              {option.label}: {option.explained}
            </li>
          ))}
        </ul>
        {stated.basis !== "unknown" && (
          <p className="text-caption text-ink-muted">
            QuickBooks ran this company&apos;s reports on the {stated.basis} basis.
          </p>
        )}
        {checked && errors.basis !== undefined && (
          <p className="text-caption text-danger">{errors.basis}</p>
        )}
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-label text-ink">Fiscal year ends</legend>
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label="Month"
            inputMode="numeric"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            {...shown(errors.month)}
          />
          <TextField
            label="Day"
            inputMode="numeric"
            value={day}
            onChange={(event) => setDay(event.target.value)}
            {...shown(errors.day)}
          />
        </div>
      </fieldset>
      <TextField
        label="Time zone"
        value={zone}
        onChange={(event) => setZone(event.target.value)}
        help="Where the company's day ends: a month or a year closes at midnight here."
        {...shown(errors.zone)}
      />
      <TextField
        label="Currency"
        value={currency}
        readOnly
        help="QuickBooks Online keeps a company's books in one currency."
      />
      {failure !== null && (
        <Notice tone="danger" label="Couldn't create the company" announce>
          {failure}
        </Notice>
      )}
      <ActionBar>
        <Button
          type="submit"
          variant="primary"
          fullWidth
          className="tablet:w-auto"
          disabled={saving}
        >
          Create the company
        </Button>
        <Button fullWidth className="tablet:w-auto" onClick={onBack} disabled={saving}>
          Choose another file
        </Button>
      </ActionBar>
    </form>
  );
}

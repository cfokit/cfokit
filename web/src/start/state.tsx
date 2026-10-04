import { createContext, useContext, useState, type ReactNode } from "react";
import type { Export } from "../quickbooks/read";

/**
 * What getting started holds between its pages, in page memory only: the export as read, and the
 * name of the company made from it. Nothing about the books goes into browser storage
 * (ADR-0049 § 2), so a reload asks for the file again — which is safe, because posting the same
 * file again replays rather than duplicates (ADR-0029).
 */
interface Started {
  exported: Export | null;
  setExported: (exported: Export | null) => void;
  company: string;
  setCompany: (company: string) => void;
}

const StartedContext = createContext<Started | null>(null);

export function StartedProvider({ children }: { children: ReactNode }) {
  const [exported, setExported] = useState<Export | null>(null);
  const [company, setCompany] = useState("");
  return (
    <StartedContext value={{ exported, setExported, company, setCompany }}>
      {children}
    </StartedContext>
  );
}

export function useStarted(): Started {
  const started = useContext(StartedContext);
  if (started === null) throw new Error("useStarted outside a StartedProvider");
  return started;
}

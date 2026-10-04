import { useNavigate } from "@tanstack/react-router";
import { ChooseExport } from "./ChooseExport";
import { CompanyForm } from "./CompanyForm";
import { StartFrame } from "./StartFrame";
import { useStarted } from "./state";

/**
 * Steps 1 and 2: the export, then the company it describes. The company's details come from the
 * export, which is why the file is chosen first (ADR-0058 § 1).
 */
export function GettingStarted() {
  const { exported, setExported, setCompany } = useStarted();
  const navigate = useNavigate();

  if (exported === null) {
    return (
      <StartFrame step={0} title="Bring in your books">
        <ChooseExport onRead={setExported} />
      </StartFrame>
    );
  }
  return (
    <StartFrame step={1} title="Your company">
      <CompanyForm
        stated={exported.company}
        currency={exported.books.commodity}
        onBack={() => setExported(null)}
        onCreated={(entityId, name) => {
          setCompany(name);
          void navigate({ to: "/companies/$entityId/import", params: { entityId } });
        }}
      />
    </StartFrame>
  );
}

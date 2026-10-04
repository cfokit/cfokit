import { Button, CopyBlock } from "../components";
import { StartFrame } from "./StartFrame";
import { useStarted } from "./state";

/**
 * The first question a person has after an import — did it all come across, and how is the
 * business doing — asked of the company just imported (ADR-0058 § 2). Every call names its entity
 * and there is no current one (the bookkeeper skill), so the prompt names it.
 */
export function firstQuestion(company: string, entityId: string): string {
  const which = company === "" ? `entity ${entityId}` : `"${company}" (entity ${entityId})`;
  return (
    `My books for ${which} are imported into CFOKit. Confirm they match QuickBooks and explain ` +
    `any differences, then summarize this year's profit and loss and my cash position.`
  );
}

/** Opens Claude Desktop on a new chat with the prompt drafted, for the person to send. */
export function claudeLink(prompt: string): string {
  return `claude://claude.ai/new?q=${encodeURIComponent(prompt)}`;
}

/** Step 5: on to Claude, with the first question already written. */
export function FirstQuestion({ entityId }: { entityId: string }) {
  const { company } = useStarted();
  const prompt = firstQuestion(company, entityId);
  return (
    <StartFrame step={4} title="Ask Claude about your books">
      <p className="text-body text-ink">
        Your books are in CFOKit. Continue in Claude Desktop, where the question below is waiting in
        a new chat for you to send. Your browser may ask to open Claude the first time.
      </p>
      <div>
        <Button variant="primary" onClick={() => window.location.assign(claudeLink(prompt))}>
          Continue in Claude
        </Button>
      </div>
      <CopyBlock label="Or paste this into Claude" text={prompt} />
    </StartFrame>
  );
}

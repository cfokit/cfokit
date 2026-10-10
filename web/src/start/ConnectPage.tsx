import { useNavigate } from "@tanstack/react-router";
import { ConnectClaude } from "../connect/ConnectClaude";
import { ActionBar, Button } from "../components";
import { StartFrame } from "./StartFrame";

/** Step 4: adding CFOKit to Claude, and the bookkeeper skill. Settings shows the same, later. */
export function ConnectPage({ entityId }: { entityId: string }) {
  const navigate = useNavigate();
  return (
    <StartFrame step={3} title="Connect Claude">
      <p className="text-body text-ink">
        Claude reaches your books through CFOKit and signs in as you. You do this once, not once per
        company, and these steps stay in <strong>Settings</strong> whenever you need them again.
      </p>
      <ConnectClaude />
      <ActionBar>
        <Button
          variant="primary"
          fullWidth
          className="tablet:w-auto"
          onClick={() => void navigate({ to: "/companies/$entityId/ask", params: { entityId } })}
        >
          Next: your first question
        </Button>
      </ActionBar>
    </StartFrame>
  );
}

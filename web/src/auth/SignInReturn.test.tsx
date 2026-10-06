import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SignInReturn } from "./SignInReturn";

const signinRedirect = vi.fn();
let error: Error | undefined;

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({ error, signinRedirect, isLoading: error === undefined }),
}));

describe("the page the issuer returns a person to", () => {
  beforeEach(() => {
    error = undefined;
    signinRedirect.mockReset();
  });

  it("says it is signing in while the code is exchanged", () => {
    render(<SignInReturn />);
    expect(screen.getByRole("status").textContent).toContain("Signing you in");
  });

  it("is never blank when the exchange fails, and offers to sign in again", async () => {
    error = new Error("No matching state found in storage");
    render(<SignInReturn />);

    // An announced notice fills its live region a moment after it appears.
    await waitFor(() => expect(document.body.textContent).toContain("sign-in didn't finish"));
    fireEvent.click(screen.getByRole("button", { name: "Sign in again" }));
    expect(signinRedirect).toHaveBeenCalledWith({ state: "/app/" });
  });
});

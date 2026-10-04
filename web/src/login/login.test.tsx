import axe from "axe-core";
import { render, screen } from "@testing-library/react";
import { createGetKcContextMock } from "keycloakify/login/KcContext";
import type { KcContextExtension, KcContextExtensionPerPage } from "./KcContext";
import KcPage from "./KcPage";

// Each page posts the form Keycloak's own template posts — the field names and the action URL
// the issuer gave it — since the issuer, not this theme, reads it. Field names are Keycloak's
// (themes/base/login/*.ftl in Keycloak 26).

const { getKcContextMock } = createGetKcContextMock({
  kcContextExtension: { themeName: "cfokit", properties: {} } satisfies KcContextExtension,
  kcContextExtensionPerPage: {} satisfies KcContextExtensionPerPage,
});

function form(container: HTMLElement) {
  const found = container.querySelector("form");
  if (found === null) throw new Error("the page has no form");
  return found;
}

function fieldNames(form: HTMLFormElement) {
  return [...form.elements].map((e) => (e as HTMLInputElement).name).filter(Boolean);
}

test("sign-in posts username and password to the issuer's login action", () => {
  const kcContext = getKcContextMock({ pageId: "login.ftl" });
  const { container } = render(<KcPage kcContext={kcContext} />);
  expect(form(container).getAttribute("action")).toBe(kcContext.url.loginAction);
  expect(fieldNames(form(container))).toEqual(expect.arrayContaining(["username", "password"]));
  expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Create an account" }).getAttribute("href")).toBe(
    kcContext.url.registrationUrl,
  );
});

test("signing in again names the account, with a way to use another", () => {
  const kcContext = getKcContextMock({
    pageId: "login.ftl",
    overrides: { usernameHidden: true, auth: { attemptedUsername: "owner@example.com" } },
  });
  render(<KcPage kcContext={kcContext} />);
  expect(screen.getByText(/owner@example\.com/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Not you?" }).getAttribute("href")).toBe(
    kcContext.url.loginRestartFlowUrl,
  );
});

test("a refused sign-in is shown beside the password, not twice", () => {
  const kcContext = getKcContextMock({
    pageId: "login.ftl",
    overrides: {
      message: { type: "error", summary: "Invalid username or password." },
      messagesPerField: {
        existsError: (...names: string[]) => names.includes("password"),
        getFirstError: () => "Invalid username or password.",
      },
    },
  });
  render(<KcPage kcContext={kcContext} />);
  expect(screen.getAllByText("Invalid username or password.")).toHaveLength(1);
  expect(screen.getByLabelText("Password").getAttribute("aria-invalid")).toBe("true");
});

test("registration asks for the profile the realm defines and a password, and no phone", () => {
  const kcContext = getKcContextMock({ pageId: "register.ftl" });
  const { container } = render(<KcPage kcContext={kcContext} />);
  expect(form(container).getAttribute("action")).toBe(kcContext.url.registrationAction);
  const names = fieldNames(form(container));
  for (const attribute of Object.keys(kcContext.profile.attributesByName)) {
    expect(names).toContain(attribute);
  }
  expect(names).toEqual(expect.arrayContaining(["password", "password-confirm"]));
  expect(screen.queryByLabelText(/phone/i)).toBeNull();
});

test("text from the issuer is shown as text, not markup", async () => {
  const kcContext = getKcContextMock({
    pageId: "error.ftl",
    overrides: { message: { type: "error", summary: "&lt;b&gt;Expired&lt;/b&gt; link" } },
  });
  const { container } = render(<KcPage kcContext={kcContext} />);
  expect(await screen.findByText("<b>Expired</b> link")).toBeTruthy();
  expect(container.querySelector("b")).toBeNull();
});

const pages = [
  "login.ftl",
  "register.ftl",
  "login-reset-password.ftl",
  "login-update-password.ftl",
  "login-otp.ftl",
  "login-config-totp.ftl",
  "info.ftl",
  "error.ftl",
  "login-page-expired.ftl",
  "logout-confirm.ftl",
] as const;

test.each(pages)("%s has no accessibility violations axe can find", async (pageId) => {
  const { container } = render(<KcPage kcContext={getKcContextMock({ pageId })} />);
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
});

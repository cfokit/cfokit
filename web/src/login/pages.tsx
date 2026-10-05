import { useState } from "react";
import type { Attribute } from "keycloakify/login";
import { Button, TextField, TextLink } from "../components";
import type { KcContext } from "./KcContext";
import { plain, SignInPage } from "./SignInPage";

// The issuer's pages CFOKit draws. Each posts the form Keycloak's own template would, with the
// same field names, to the action URL the issuer gave it; nothing here decides anything.

type Page<Id extends KcContext["pageId"]> = Extract<KcContext, { pageId: Id }>;

function fieldError(kc: KcContext, ...names: [string, ...string[]]): string | undefined {
  return kc.messagesPerField.existsError(...names)
    ? plain(kc.messagesPerField.getFirstError(...names))
    : undefined;
}

/** The message, unless a field already shows it. */
function pageMessage(kc: KcContext, ...fields: string[]) {
  const [first, ...rest] = fields;
  if (first !== undefined && kc.messagesPerField.existsError(first, ...rest)) return undefined;
  return kc.message;
}

/** One submit per form: a second press while the first is in flight does nothing. */
function useSubmitOnce() {
  const [submitting, setSubmitting] = useState(false);
  return [submitting, () => setSubmitting(true)] as const;
}

export function Login({ kcContext: kc }: { kcContext: Page<"login.ftl"> }) {
  const [submitting, onSubmit] = useSubmitOnce();
  const error = fieldError(kc, "username", "password");
  return (
    <SignInPage title="Sign in" message={pageMessage(kc, "username", "password")}>
      <form
        method="post"
        action={kc.url.loginAction}
        onSubmit={onSubmit}
        className="flex flex-col gap-6"
      >
        {kc.usernameHidden === true && kc.auth.attemptedUsername !== undefined && (
          <p className="text-body text-ink">
            As {kc.auth.attemptedUsername}.{" "}
            <TextLink href={kc.url.loginRestartFlowUrl}>Not you?</TextLink>
          </p>
        )}
        {kc.usernameHidden !== true && (
          <TextField
            label="Email"
            name="username"
            type="email"
            autoComplete="username"
            defaultValue={kc.login.username ?? ""}
            required
            autoFocus
          />
        )}
        <TextField
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          error={error}
        />
        {kc.auth.selectedCredential !== undefined && (
          <input type="hidden" name="credentialId" value={kc.auth.selectedCredential} />
        )}
        <Button type="submit" variant="primary" fullWidth disabled={submitting}>
          Sign in
        </Button>
      </form>
      <div className="flex flex-col gap-3">
        {kc.realm.resetPasswordAllowed && (
          <TextLink href={kc.url.loginResetCredentialsUrl}>Forgot your password?</TextLink>
        )}
        {kc.realm.password && kc.realm.registrationAllowed && !kc.registrationDisabled && (
          <p className="text-body text-ink">
            New to CFOKit? <TextLink href={kc.url.registrationUrl}>Create an account</TextLink>
          </p>
        )}
      </div>
    </SignInPage>
  );
}

const LABELS: Record<string, string> = {
  email: "Email",
  firstName: "First name",
  lastName: "Last name",
  username: "Username",
};

function ProfileField({ kc, attribute }: { kc: Page<"register.ftl">; attribute: Attribute }) {
  return (
    <TextField
      label={LABELS[attribute.name] ?? attribute.displayName ?? attribute.name}
      name={attribute.name}
      type={attribute.name === "email" ? "email" : "text"}
      autoComplete={attribute.autocomplete}
      defaultValue={attribute.value ?? ""}
      required={attribute.required}
      readOnly={attribute.readOnly}
      error={fieldError(kc, attribute.name)}
    />
  );
}

export function Register({ kcContext: kc }: { kcContext: Page<"register.ftl"> }) {
  const [submitting, onSubmit] = useSubmitOnce();
  const attributes = Object.values(kc.profile.attributesByName);
  return (
    <SignInPage
      title="Create your account"
      message={pageMessage(kc, ...attributes.map((a) => a.name), "password", "password-confirm")}
    >
      <form
        method="post"
        action={kc.url.registrationAction}
        onSubmit={onSubmit}
        className="flex flex-col gap-6"
      >
        {attributes.map((attribute) => (
          <ProfileField key={attribute.name} kc={kc} attribute={attribute} />
        ))}
        {kc.passwordRequired && (
          <>
            <TextField
              label="Password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              error={fieldError(kc, "password")}
            />
            <TextField
              label="Confirm password"
              name="password-confirm"
              type="password"
              autoComplete="new-password"
              required
              error={fieldError(kc, "password-confirm")}
            />
          </>
        )}
        <Button type="submit" variant="primary" fullWidth disabled={submitting}>
          Create account
        </Button>
      </form>
      <p className="text-body text-ink">
        Already have an account? <TextLink href={kc.url.loginUrl}>Sign in</TextLink>
      </p>
    </SignInPage>
  );
}

export function ResetPassword({ kcContext: kc }: { kcContext: Page<"login-reset-password.ftl"> }) {
  const [submitting, onSubmit] = useSubmitOnce();
  return (
    <SignInPage title="Reset your password" message={pageMessage(kc, "username")}>
      <p className="text-body text-ink">
        Enter your email and we&apos;ll send you a link to choose a new password.
      </p>
      <form
        method="post"
        action={kc.url.loginAction}
        onSubmit={onSubmit}
        className="flex flex-col gap-6"
      >
        <TextField
          label="Email"
          name="username"
          type="email"
          autoComplete="username"
          defaultValue={kc.auth.attemptedUsername ?? ""}
          required
          autoFocus
          error={fieldError(kc, "username")}
        />
        <Button type="submit" variant="primary" fullWidth disabled={submitting}>
          Send the link
        </Button>
      </form>
      <TextLink href={kc.url.loginUrl}>Back to sign in</TextLink>
    </SignInPage>
  );
}

export function UpdatePassword({
  kcContext: kc,
}: {
  kcContext: Page<"login-update-password.ftl">;
}) {
  const [submitting, onSubmit] = useSubmitOnce();
  return (
    <SignInPage
      title="Choose a new password"
      message={pageMessage(kc, "password", "password-confirm")}
    >
      <form
        method="post"
        action={kc.url.loginAction}
        onSubmit={onSubmit}
        className="flex flex-col gap-6"
      >
        <TextField
          label="New password"
          name="password-new"
          type="password"
          autoComplete="new-password"
          required
          autoFocus
          error={fieldError(kc, "password")}
        />
        <TextField
          label="Confirm password"
          name="password-confirm"
          type="password"
          autoComplete="new-password"
          required
          error={fieldError(kc, "password-confirm")}
        />
        <Button type="submit" variant="primary" fullWidth disabled={submitting}>
          Save password
        </Button>
      </form>
    </SignInPage>
  );
}

export function Otp({ kcContext: kc }: { kcContext: Page<"login-otp.ftl"> }) {
  const [submitting, onSubmit] = useSubmitOnce();
  const credential = kc.otpLogin.selectedCredentialId ?? kc.otpLogin.userOtpCredentials[0]?.id;
  return (
    <SignInPage title="Enter your code" message={pageMessage(kc, "totp")}>
      <form
        method="post"
        action={kc.url.loginAction}
        onSubmit={onSubmit}
        className="flex flex-col gap-6"
      >
        {credential !== undefined && (
          <input type="hidden" name="selectedCredentialId" value={credential} />
        )}
        <TextField
          label="Code from your authenticator app"
          name="otp"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          autoFocus
          error={fieldError(kc, "totp")}
        />
        <Button type="submit" variant="primary" fullWidth disabled={submitting}>
          Sign in
        </Button>
      </form>
      {kc.auth?.showTryAnotherWayLink === true && (
        <form method="post" action={kc.url.loginAction}>
          <input type="hidden" name="tryAnotherWay" value="on" />
          <Button type="submit" variant="link">
            Try another way
          </Button>
        </form>
      )}
    </SignInPage>
  );
}

export function ConfigTotp({ kcContext: kc }: { kcContext: Page<"login-config-totp.ftl"> }) {
  const [submitting, onSubmit] = useSubmitOnce();
  const manual = kc.mode === "manual";
  return (
    <SignInPage title="Set up two-step sign-in" message={pageMessage(kc, "totp", "userLabel")}>
      <ol className="flex list-decimal flex-col gap-3 pl-6 text-body text-ink">
        <li>Open an authenticator app on your phone, such as Google Authenticator or 1Password.</li>
        {manual ? (
          <li>
            Add an account and enter this key:{" "}
            <code className="break-all text-label">{kc.totp.totpSecretEncoded}</code>.{" "}
            <TextLink href={kc.totp.qrUrl}>Scan a code instead</TextLink>
          </li>
        ) : (
          <li className="flex flex-col gap-3">
            <span>Scan this code with it.</span>
            <img
              src={`data:image/png;base64,${kc.totp.totpSecretQrCode}`}
              alt="QR code for your authenticator app"
              width={180}
              height={180}
              className="self-start rounded-sm bg-surface"
            />
            <TextLink href={kc.totp.manualUrl}>Can&apos;t scan it? Enter a key instead</TextLink>
          </li>
        )}
        <li>Enter the code the app shows.</li>
      </ol>
      <form
        method="post"
        action={kc.url.loginAction}
        onSubmit={onSubmit}
        className="flex flex-col gap-6"
      >
        <input type="hidden" name="totpSecret" value={kc.totp.totpSecret} />
        {kc.mode != null && <input type="hidden" name="mode" value={kc.mode} />}
        <TextField
          label="Code"
          name="totp"
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          error={fieldError(kc, "totp")}
        />
        <TextField
          label="Device name"
          name="userLabel"
          help="So you can tell your devices apart later."
          error={fieldError(kc, "userLabel")}
        />
        <Button type="submit" variant="primary" fullWidth disabled={submitting}>
          Turn on
        </Button>
      </form>
    </SignInPage>
  );
}

export function Info({ kcContext: kc }: { kcContext: Page<"info.ftl"> }) {
  const next = kc.skipLink ? undefined : (kc.pageRedirectUri ?? kc.actionUri ?? kc.client.baseUrl);
  const header = plain(kc.messageHeader ?? "");
  return (
    <SignInPage title={header === "" ? "One more thing" : header}>
      <p className="text-body text-ink">{plain(kc.message.summary)}</p>
      {next !== undefined && <TextLink href={next}>Continue</TextLink>}
    </SignInPage>
  );
}

export function ErrorPage({ kcContext: kc }: { kcContext: Page<"error.ftl"> }) {
  const back = kc.skipLink === true ? undefined : kc.client?.baseUrl;
  return (
    <SignInPage title="Something went wrong" message={kc.message}>
      {back !== undefined && <TextLink href={back}>Back to CFOKit</TextLink>}
    </SignInPage>
  );
}

export function PageExpired({ kcContext: kc }: { kcContext: Page<"login-page-expired.ftl"> }) {
  return (
    <SignInPage title="This page expired">
      <p className="text-body text-ink">
        It was open too long. Start again, or carry on from here.
      </p>
      <div className="flex flex-col gap-3">
        <TextLink href={kc.url.loginRestartFlowUrl}>Start again</TextLink>
        <TextLink href={kc.url.loginAction}>Carry on</TextLink>
      </div>
    </SignInPage>
  );
}

export function LogoutConfirm({ kcContext: kc }: { kcContext: Page<"logout-confirm.ftl"> }) {
  const [submitting, onSubmit] = useSubmitOnce();
  return (
    <SignInPage title="Sign out of CFOKit?" message={kc.message}>
      <form
        method="post"
        action={kc.url.logoutConfirmAction}
        onSubmit={onSubmit}
        className="flex flex-col gap-6"
      >
        <input type="hidden" name="session_code" value={kc.logoutConfirm.code} />
        <Button
          type="submit"
          name="confirmLogout"
          value="Sign out"
          variant="primary"
          fullWidth
          disabled={submitting}
        >
          Sign out
        </Button>
      </form>
      {!kc.logoutConfirm.skipLink && kc.client.baseUrl !== undefined && (
        <TextLink href={kc.client.baseUrl}>Back to CFOKit</TextLink>
      )}
    </SignInPage>
  );
}

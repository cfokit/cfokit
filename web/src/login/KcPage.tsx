import { lazy, Suspense } from "react";
import DefaultPage from "keycloakify/login/DefaultPage";
import Template from "keycloakify/login/Template";
import type { KcContext } from "./KcContext";
import { useI18n } from "./i18n";
import {
  ConfigTotp,
  ErrorPage,
  Info,
  Login,
  LogoutConfirm,
  Otp,
  PageExpired,
  Register,
  ResetPassword,
  UpdatePassword,
} from "./pages";

const UserProfileFormFields = lazy(() => import("keycloakify/login/UserProfileFormFields"));

/**
 * The issuer's sign-in theme (ADR-0054 § 1). CFOKit draws the pages its realm's flows reach; any
 * other page Keycloak serves keeps Keycloakify's default rendering until a flow needs it.
 */
export default function KcPage({ kcContext }: { kcContext: KcContext }) {
  const { i18n } = useI18n({ kcContext });
  switch (kcContext.pageId) {
    case "login.ftl":
      return <Login kcContext={kcContext} />;
    case "register.ftl":
      return <Register kcContext={kcContext} />;
    case "login-reset-password.ftl":
      return <ResetPassword kcContext={kcContext} />;
    case "login-update-password.ftl":
      return <UpdatePassword kcContext={kcContext} />;
    case "login-otp.ftl":
      return <Otp kcContext={kcContext} />;
    case "login-config-totp.ftl":
      return <ConfigTotp kcContext={kcContext} />;
    case "info.ftl":
      return <Info kcContext={kcContext} />;
    case "error.ftl":
      return <ErrorPage kcContext={kcContext} />;
    case "login-page-expired.ftl":
      return <PageExpired kcContext={kcContext} />;
    case "logout-confirm.ftl":
      return <LogoutConfirm kcContext={kcContext} />;
    default:
      return (
        <Suspense>
          <DefaultPage
            kcContext={kcContext}
            i18n={i18n}
            Template={Template}
            doUseDefaultCss
            UserProfileFormFields={UserProfileFormFields}
            doMakeUserConfirmPassword
          />
        </Suspense>
      );
  }
}

import type { ExtendKcContext } from "keycloakify/login";
import type { KcEnvName, ThemeName } from "../kc.gen";

// What the issuer hands the sign-in theme on each of its pages, as window.kcContext.
export interface KcContextExtension {
  themeName: ThemeName;
  properties: Record<KcEnvName, string>;
}

export type KcContextExtensionPerPage = Record<never, never>;

export type KcContext = ExtendKcContext<KcContextExtension, KcContextExtensionPerPage>;

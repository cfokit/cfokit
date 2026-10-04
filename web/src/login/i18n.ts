import { i18nBuilder } from "keycloakify/login";
import type { ThemeName } from "../kc.gen";

// Keycloak's own messages, for the pages this theme leaves to Keycloakify's defaults. The pages
// CFOKit draws write their copy in English directly.
export const { useI18n } = i18nBuilder.withThemeName<ThemeName>().build();

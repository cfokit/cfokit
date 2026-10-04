/** Why an export will not be read: one of the codes the server uses for the same refusal. */
export type RefusalCode =
  "import_too_large" | "import_refused" | "unreadable_figure" | "unreadable_archive";

/** The export will not be read, and why. */
export class Refused extends Error {
  constructor(
    readonly code: RefusalCode,
    detail: string,
  ) {
    super(detail);
  }
}

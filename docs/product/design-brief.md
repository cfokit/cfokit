# Design brief: the web client

What the web client must look like and handle, written to be given to Claude Design. It describes
behavior and states; the designs decide how they look.

## How this is used

**The design system comes first.** Claude Design produces its tokens — color, type, spacing,
radii — and the web client's Tailwind theme is generated from that `tokens.json`, so the designs
and the product share one source for how things look. Once the client's components exist in code,
they are published back to the design system with `/design-sync`, and later designs are drawn with
the real components rather than look-alikes.

**The screens come second**, drawn on a Claude Design canvas with that system. Claude Code reads a
canvas directly from its link — artboards, index and tokens — so designs reach the codebase without
screenshots. The artboards stay on claude.ai as the reference; only `tokens.json` enters the
repository.

The two prompts below can be pasted into Claude Design as they are, or Claude Code can build the
canvas from this file.

## Prompt 1 — the design system

> Create a design system for **CFOKit**, a bookkeeping and finance product for small businesses.
> The people using it run a business; they are not accountants. It should feel trustworthy, calm
> and precise — a financial tool you would let near your company's books — without looking like a
> bank or a generic SaaS dashboard.
>
> Define tokens for color (a neutral ground, text, one or two accents, and semantic colors for
> success, warning, error and info that stay distinguishable without relying on red versus green),
> typography (a display face and a body face, plus a tabular-figures style for money, which appears
> everywhere), spacing, radii, borders and shadows. Money must be easy to scan in columns:
> right-aligned, tabular figures, clear negatives.
>
> The system covers phone, tablet and desktop: breakpoints, column grids and gutters for each,
> a compact size of the headline, heading and total-figure styles for phones, a 16px size for text
> typed into inputs (iOS zooms into anything smaller), and a 44px minimum tap target.
>
> Include the core components: buttons (primary, secondary, destructive, link), text inputs with
> labels and errors, file drop zone, progress bar, step indicator, alert or notice, data table with
> numeric columns, card, and the app frame (a header with the company name, the signed-in person,
> and a way to sign out). Everything meets WCAG AA contrast, and every interactive element has a
> visible focus state.

## Prompt 2 — onboarding

> Using the CFOKit design system, design the onboarding flow for a new customer at three sizes:
> phone (390 wide), tablet (834 wide) and desktop (1440 wide). CFOKit is a progressive web app, used
> in a browser or installed to a home screen. The flow: create an account → create
> the company → import its books from QuickBooks → see whether the books agree with QuickBooks →
> return to Claude, where their assistant explains the results.
>
> **Sign-in screens.** These are rendered by the identity provider, so they sit in a simple frame of
> their own, without the app's header.
>
> 1. Sign in — email and password, "Continue with Google", "Continue with Microsoft", "Sign in with
>    a passkey", links to sign up and to reset a password.
> 2. Sign up — name, email, password, and the same Google and Microsoft options.
> 3. Verify your email — check your inbox, resend.
> 4. Reset password — request a link, then set a new password.
> 5. Two-step verification — set up an authenticator app (a QR code and a code to confirm), and the
>    prompt for a code at sign-in.
> 6. Add a passkey — a short explanation and one action.
>
> **In the app**, inside the app frame:
>
> 7. Create your company — company name, accounting basis (accrual or cash, each explained in one
>    plain sentence), fiscal year end, currency, time zone. One primary action.
> 8. Import your books — two sentences on what to export from QuickBooks and how, and a drop zone
>    for the export (a .zip).
> 9. Reading the export — a brief progress state.
> 10. Export refused — a plain-language reason (too large, not a QuickBooks export, damaged) and
>     what to do about it.
> 11. What will be imported — the period covered, how many transactions and accounts, anything that
>     will not be imported and why, accounts QuickBooks gave no type for, and a note when
>     QuickBooks' reports use a different accounting basis from its transactions. Actions: Import,
>     Cancel.
> 12. Importing — progress through thousands of transactions, which can take several minutes. Say
>     that it is safe to leave: after a reload, choosing the same file again picks up where it
>     stopped, and nothing is counted twice.
> 13. Do the books agree? — lead with the answer ("25 of 27 accounts match QuickBooks exactly"),
>     then each account that differs, with both figures side by side. A difference explained by
>     the accounting basis is marked as expected, not as an error.
> 14. Back to Claude — the import is finished; return to your Claude conversation, where your
>     assistant walks through the results. This is an instruction, not an automatic redirect.
>
> **States that apply anywhere:** signed out while working (sign in again and return to the same
> step), lost access to the company, the server cannot be reached, a second browser tab open on the
> same step, offline in the installed app (it says so and changes nothing), and a new version ready
> ("Reload to update", never automatic).
>
> On a phone, the primary action sits in a bar at the bottom of the screen; the drop zone is a
> "Choose file" button that opens the device's file picker; and the reconciliation's two-figure
> table becomes a list with the account name above its two labelled figures.
>
> No filler or lorem ipsum: use realistic figures from a small consulting business, about 5,500
> transactions over eight years. Names read from a file are shown as plain text. Accounting terms
> get a one-line plain-English explanation where they appear. Touch targets are at least 44px.

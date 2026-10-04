CFOKit is a bookkeeper agent: a small business's books, done for it. The people using it run the business; they are not
accountants. Everything here serves one impression: this is a precise instrument you can trust
with your company's money, and it speaks plainly.

## Content

- Write in plain English, second person ("your books", "you're the owner"), sentence case
  everywhere, including buttons and headings.
- Explain an accounting term in one line the first time it appears on a screen, in `caption`:
  "Accrual: income counts when you invoice, not when you're paid."
- Lead with the answer. "25 of 27 accounts match QuickBooks exactly" comes before any detail.
- Buttons say exactly what happens: "Import", "Create company", "Try another file". A result
  says what happened: "Imported 5,553 transactions."
- Errors say what went wrong and what to do, without apology: "This file isn't a QuickBooks
  export. Choose the .zip QuickBooks gave you, or export your books again."
- No emoji, no exclamation marks, no filler figures. Placeholders look like placeholders:
  [COMPANY NAME].
- Names read from a customer's file (accounts, payees, descriptions) are shown exactly as
  written, as plain text.

## Money

- Set every amount in `money`, and every total or headline figure in `money-total`, with
  tabular figures (`font-variant-numeric: tabular-nums`). Right-align amounts in columns.
- Show negatives in parentheses, the accounting convention: (1,250.00). Never show a negative
  by color alone, and never in red.
- Show the currency once, in the column header or beside a total ("USD"), not on every row.
- Show what the books computed. Never sum, round or convert an amount on the page.

## Color

- Set pages on `paper`. Use `surface` only for an object that stands apart (a form panel, a
  dialog, the sign-in card); use `sunken` for wells inside it (the drop zone, a table header).
- Text is `ink`, secondary text `ink-muted`. Both read on `paper`, `surface` and `sunken` in
  both themes.
- `accent` is the only interactive color: primary buttons (with `on-accent` text), links, the
  current step, the focus ring. Nothing decorative uses it.
- `ochre` marks the one thing on a screen the reader should look at next: a differing row, an
  account with no type. It is never a state. Text on it is `ink` in light and `paper` in dark.
- States are `success` (agrees, finished), `warning` (look, but not wrong) and `danger`
  (refused, failed, destructive). Each always comes with a word: "Matches", "Expected
  difference", "Differs". `success` is teal-blue so nothing depends on telling red from green.
- Separate with hairline `rule`s, not shadows. `shadow-overlay` is for dialogs and menus only.
- Control borders (inputs, checkboxes, the drop zone) use `control-border`, never `rule`.

## Type

- `display` (Archivo Narrow) once per screen for the headline; `heading` for section titles.
- `title` for panels; `body` for running text; `label` for form labels and column headers;
  `caption` for help text.
- Below `bp-tablet`, `display-compact`, `heading-compact` and `money-total-compact` replace
  `display`, `heading` and `money-total`. Everything else keeps its size on every device.
- Text typed into an input is `input` (16px) everywhere; smaller, and iOS Safari zooms the page.
- Keep running text within `reading-max`.
- Both faces ship with this system as files under `fonts/`: Public Sans at 400, 500 and 600,
  Archivo Narrow at 600 and 700, each under the SIL Open Font License 1.1, whose texts are under
  `licenses/`. The product serves these same files from its own origin, with the licenses beside
  them; nothing loads from a font service. The families' fallbacks are the system interface font,
  so text shows before the files arrive.

## Space and shape

- Space with the scale only: `space-1` to `space-10`. Fields sit `space-6` apart; a label sits
  `space-2` above its input. Page gutters are in Devices.
- Corners are small, as befits an instrument: `radius-sm` for inputs and pills, `radius-md`
  for buttons and the drop zone, `radius-lg` for surfaces. Nothing is pill-shaped but a status
  pill.
- Every interactive element shows `focus-ring`: `stroke-focus` solid, offset 2px. Every tap
  or click target is at least `target-min`.

## Devices

CFOKit is one progressive web app: the same pages in a browser on a desktop, a tablet or a
phone, and installed to a home screen. Design every screen at all three sizes: a phone at 390
wide, a tablet at 834 (portrait) and 1194 (landscape), a desktop at 1440.

- **Phone**, below `bp-tablet`: `columns-phone`, `gutter-phone`. One column. The primary action
  sits in a bar pinned to the bottom of the screen, in thumb reach.
- **Tablet**, from `bp-tablet`: `columns-tablet`, `gutter-tablet`. Forms stay one column at
  `reading-max`; summaries may sit beside their detail. A tablet in landscape is at or past
  `bp-desktop` and gets the desktop layout.
- **Desktop**, from `bp-desktop`: `columns-desktop`, `gutter-desktop`. Content stops widening at
  `content-max` from `bp-wide` and centers on `paper`.
- **Touch and pointer are equal.** Nothing is reachable only on hover: a hover state repeats
  something already visible. Never make a person drag to do something; drag is a shortcut beside
  a button.
- **Inputs ask for the right keyboard**: amounts with a decimal keypad, email with the email
  keyboard, and the browser's own autofill for names, emails and passwords.
- **Orientation.** Every screen works in both orientations on a phone and a tablet.

### Installed

- The app fills the screen edge to edge, so the app frame and the bottom action bar add the
  device's safe-area insets to `bar-height`; nothing sits under a notch or the home indicator.
- The browser's toolbar color is `paper` in each theme, so the installed app reads as one surface.
- The home-screen icon is `cfokit-icon.svg`, kept inside the central 80% of its tile so a
  rounded or circular mask never clips the mark. The launch screen is `paper` with
  `cfokit-lockup.svg` centered (`cfokit-lockup-dark.svg` in dark).
- Offline, a screen says so in a `warning` notice ("You're offline. Your books are unchanged;
  this page will update when you reconnect.") and keeps what it last showed. Nothing that
  changes the books is attempted offline.
- When a new version is ready, a notice offers "Reload to update". It never reloads by itself,
  because a reload could interrupt an import.

## Components

These describe how the web client's components look and behave. The components themselves
live in its code and are published into this system from there.

- **Button.** Primary: `accent` fill, `on-accent` text, `radius-md`, `label` weight at `body`
  size, at least `target-min` tall. Secondary: `surface` fill, `control-border` hairline, `ink`
  text. Destructive: `danger` text on `surface`, never a filled red. Link: `accent` text,
  underlined. One primary button per screen; below `bp-tablet` it spans the bottom action bar.
- **Input.** `surface` fill, `control-border` hairline, `radius-sm`, `label` above and `caption`
  help below. An error puts `danger` on the border and a sentence below, not a color alone.
- **Drop zone.** `sunken` fill, dashed `control-border`, `radius-md`, one sentence and a
  "Choose file" button. While a file is over it: `accent` border. On touch devices there is
  nothing to drop: the zone is the "Choose file" button, which opens the device's file picker.
- **Progress.** A bar on `sunken` filled with `accent`, the count beside it in `money`
  ("2,000 of 5,556"). Never a spinner alone for work longer than a few seconds.
- **Step indicator.** The onboarding steps as `label` text: done in `ink-muted` with a check,
  current in `accent`, later in `ink-muted`.
- **Notice.** A `surface` panel with a 1px border in the state's color and a leading word in
  that color ("Refused", "Expected difference"), body text in `ink`. No colored left bar.
- **Money table.** `label` headers on `sunken`, rows divided by `rule`, amounts in `money`
  right-aligned, a differing row marked with an `ochre` tick in its first cell. Totals from the
  API in `money-total` beneath, not summed on the page. Below `bp-tablet` a table of two figures
  per row (ours and QuickBooks') becomes a list: the account name on one line and the two
  figures labeled beneath it. A wider table keeps its columns, scrolls sideways within its own
  frame and keeps the first column fixed; the page never scrolls sideways.
- **Card.** Only for an object that stands apart: `surface`, `radius-lg`, a `rule` border,
  `space-6` padding. Lists of rows are tables, not cards.
- **App frame.** A `bar-height` header on `surface` with a bottom `rule`: the mark and the
  company name in `title`, the signed-in person and "Sign out" at the right in `body`. Below
  `bp-tablet` the person and "Sign out" move into a menu opened from a button at the right.
  Sign-in screens have no app frame: `cfokit-lockup.svg` above a single `surface` card on
  `paper`, the card filling the width on a phone.
- **Dialog.** A `surface` panel with `radius-lg` and `shadow-overlay`, centered. Below
  `bp-tablet` it is a sheet rising from the bottom edge, full width, with its actions in thumb
  reach.

## Iconography

No icon set is chosen yet. Use words; where an icon is unavoidable (a check on a done step,
a file), draw it as a 1.5px stroke in the text color it sits beside, never as an emoji. Icons
take their geometry from the mark: square ends, right angles, no rounded strokes.

## Logo

The mark is a T-account, the oldest picture of double-entry: a bar over a divider, debits on
the left and credits on the right. One entry on each side, one of them in `ochre` (the entry
the reader can trace), and a double rule under both sides, the accountant's sign that the
totals agree. It says what CFOKit promises: books that balance, and every number explains
itself.

- Use `cfokit-lockup.svg` (mark and name) wherever the brand is introduced: the site header,
  the README on GitHub, a statement's cover page, the sign-in card. On dark grounds use
  `cfokit-lockup-dark.svg`.
- Use `cfokit-mark.svg` alone only where the name already appears nearby or space is square:
  the app frame beside the company name, an avatar. Dark grounds take `cfokit-mark-dark.svg`.
- Use `cfokit-icon.svg` (the mark reversed out of an `ink` tile, simplified to one entry a
  side) for favicons, app icons and anything under 24px. The full mark's double rules fill in
  below that size.
- Keep clear space of half the mark's height on every side. Never recolor, outline, add a
  shadow, or move the ochre entry to the left side.
- The name is Archivo Narrow 700, outlined in the SVG. In running text write "CFOKit": capital
  C, F, O, K, lowercase "it".

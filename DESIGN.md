---
name: Binder
description: AI administrative agent, 100% local
colors:
  primary: "oklch(0.28 0.07 262)"
  primary-dark: "oklch(0.93 0.004 260)"
  background: "oklch(0.985 0.003 250)"
  background-dark: "oklch(0.175 0.002 260)"
  foreground: "oklch(0.22 0.03 260)"
  foreground-dark: "oklch(0.94 0.002 260)"
  card: "oklch(1 0 0)"
  card-dark: "oklch(0.208 0.003 260)"
  sidebar: "oklch(0.975 0.004 250)"
  sidebar-dark: "oklch(0.155 0.002 260)"
  muted-foreground: "oklch(0.52 0.02 258)"
  accent: "oklch(0.95 0.018 255)"
  border: "oklch(0.925 0.008 255)"
  destructive: "oklch(0.55 0.2 25)"
typography:
  page-title:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    letterSpacing: "-0.025em"
  stat:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
  title:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
  body:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  label:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
  overline:
    fontFamily: "Geist Variable, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    letterSpacing: "0.025em"
rounded:
  base: "0.75rem"
  md: "0.6rem"
  xl: "1.05rem"
  pill: "9999px"
spacing:
  page-x: "40px"
  page-y: "32px"
  card: "16px"
  row: "12px 20px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.background}"
    rounded: "{rounded.base}"
    height: "40px"
    padding: "0 16px"
  input:
    rounded: "{rounded.base}"
    height: "40px"
    padding: "4px 12px"
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.xl}"
    padding: "{spacing.card}"
  nav-item-active:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.primary}"
    rounded: "{rounded.base}"
    padding: "6px 12px"
---

# Design System: Binder

Source of truth: `frontend/src/index.css` (CSS variables, light `:root` and `.dark`). Tokens above
mirror it; if they disagree, the CSS wins. Stack: Tailwind v4 + shadcn/ui (`base-nova`, Base UI
primitives), Phosphor icons (`@phosphor-icons/react`, `*Icon` names), Geist Variable.
Icon weights: regular, bold, fill, light only; the build drops the others (`ICON_WEIGHTS` in
`vite.config.ts`), so a new weight must be added there first or its icons render empty.

## Overview

**Creative North Star: "The Personal Secretary"**

Binder greets you, tells you what needs your attention today, and keeps everything else quietly in
order. The interface is an Operate surface: calm, dense enough to scan, never decorative. Ink navy
carries the brand; colour elsewhere is a signal (urgency, category), never ornament. Dark mode is a
the light theme inverted: neutral graphite surfaces (no blue cast), depth by lightness steps,
the primary as paper with ink text.

**Key Characteristics:**
- Navy brand, cool near-white surfaces, one accent family.
- Colour only for meaning: urgency (red/amber/emerald) and category tones.
- Flat surfaces, hairline rings and borders, generous 12px-based radii.
- Plain sentences as headings and hints; no status badges or pulsing dots.

## Colors

### Primary
- **Ink Navy** (`primary`): primary buttons, logo tile, active nav text, links. Turns **Paper**
  (`primary-dark`, near-white with ink text) in dark mode: navy on paper in light, paper on ink
  in dark, the brightest thing on screen in both. Marks drawn on a document page (white in both
  themes) use `paper-ink`, the light navy, in both themes.

### Neutral
- **Cool Paper** (`background`) page; **White** (`card`) cards and popovers; **Sidebar Mist**
  (`sidebar`) navigation; **Ink** (`foreground`) text; **Slate** (`muted-foreground`) secondary
  text; **Haze** (`accent`) hover and active fills; hairline `border`.
- Dark: surfaces lighten as they come forward: sidebar < background < card < popover. Borders are
  white at 6-12% alpha. Dark surfaces are neutral: hue only in the signals.

### Signals (Tailwind palette, not tokens)
- Urgency (`urgencyStyles`, `lib/format.ts`): late/urgent red, soon amber, later emerald; as dot,
  pill (`-50` bg / `-700` text; dark `-500/15` bg / `-300` text) or text.
- Categories (`CATEGORY_STYLE`, `lib/categories.tsx`): one hue + Phosphor icon per category, pastel
  tile in light, a `-400/12` tint with a `-300` icon in dark.
- `destructive` red for delete actions, always as a soft tint (`/10` bg), never solid.

**The Signal-Only Rule.** Hue outside navy appears only to say something (urgency, category,
status). In dark mode a tinted card goes neutral: the hue stays on the icon and hint only.

## Typography

**Font:** Geist Variable for everything (headings reuse `--font-sans`). No display or mono face.

- **Page title** 24px/600, tight tracking: one per page, via `PageHeader`.
- **Stat** 30px/600: home stat cards only.
- **Section title** 16px/600 inside cards.
- **Body** 14px: default UI text; inputs are 16px on mobile, 14px from `md`.
- **Label** 12px/500: hints, metadata, reasons ("Due in 3 days").
- **Overline** 11px/500 uppercase, slight tracking: sidebar section titles only.

**The Sentence Rule.** Headings and hints are plain sentences in sentence case, translated via the
i18n catalogs; never all-caps outside the sidebar overline.

**Text size** (Settings: Normal, Large, Larger) sets the root font size (100, 112.5, 125%), so
every size above is in `rem` and scales with it: write `text-[0.6875rem]`, never `text-[11px]`
(the desktop title bar is the one exception). Breakpoints do not follow it (media queries ignore
the root size): a layout that must stack when the text grows uses a container query
(`@container`, `@3xl:`), as the Language and appearance cards do.

## Layout

Fixed 240px sidebar (`md`+): the navy **＋ Add** button first (a menu: "Scan with your phone",
highlighted, then "Choose a file"), then three 44px rows: To do (with the count
of cards that need the user), My papers, Life events; the profile row pinned bottom opens a menu
with Settings, History and Trash. Below `md`: a slim top bar (logo, profile button) and a fixed
bottom bar of four 64px cells: the three places (icon over label) and a round navy ＋. The ask bar
(robot icon, input, Ctrl K hint, navy send button; `max-w-2xl`, centred on the content) is fixed at
the bottom of every page, just above the bottom bar on a phone; it opens the agent with the typed
question. Content `px-4 pt-6 pb-44` mobile (room for both bars), `px-8 pb-28` desktop. Page header then content, `mb-7`. To do: full width and left-aligned like every page (detail sentences capped at 70ch),
greeting and one-sentence summary, then one card per item that needs the user, urgent first,
the import report on top; what is only worth knowing comes after, quieter, as rows of one card
under "Good to know"; nothing to do: a large green check and "All in order ✓". First launch (no document yet):
"Tell me about yourself", one question per screen in a card (progress bars, full-width answer
buttons, 2 columns from `sm`), then "The papers you should have" (scan and file buttons, then
the list: area icon, title, why, how long to keep, "Here" or "To add"); demo and restore stay
quiet at the bottom. My papers: the area tiles, then a row "The papers you should have" (opens
the list in a side sheet), search, person chips and the list; tabs Documents / Calendar /
Archives. Life events: "In
progress" on top when there is any, the eight life events as large rows in a 1-2-3 column grid
(icon tile, title, one-line hint, chevron), each opening a dialog of its sub-actions (same rows,
smaller), then "Other procedures" and the "Ask Binder" fallback. Settings: one section per row, title and
description on the left (16-20rem), cards on the right.
Grids: `sm:grid-cols-3` stats, `lg:grid-cols-2` sections, gaps 16-24px. Lists are full-width rows
(`px-5 py-3`) divided by hairlines inside a card.

## Elevation & Depth

Flat. Cards use a 1px ring (`foreground/10`) or border, no resting shadow. `shadow-sm` appears only
on hover of clickable cards. Dark mode conveys depth by surface lightness, not shadow. Focus is a
3px `ring/50` halo on the shadcn controls (with their `ring` border), a 2px solid `ring` outline
offset 2px on links, plain buttons and custom controls: always at least 3:1 against the surface.

## Shapes

`--radius` 0.75rem drives the scale (sm 0.6x … 4xl 2.6x). Buttons, inputs, nav items, icon tiles:
`rounded-lg` (12px). Cards: `rounded-xl` (~17px). Badges and pills: fully round. Status dots: 8px
circles with a 4px soft ring.

## Motion

Binder should feel light, not bureaucratic: things move when it says something, never to
decorate. Utilities in `index.css`, all one-shot fades and switched off by
`prefers-reduced-motion`. **No transform animations** (no slide, scale, rotate or lift): opacity
and colour only.

- `animate-page`: each page fades in (220ms). A filter in the address does not replay it.
- `animate-rise`: cards and tiles fade in one after the other (`--i` index, 45ms apart, capped);
  a card that arrives later fades in on its own.
- `animate-step`: a new question or step fades in.
- `animate-pop`: a reward or a change worth noticing (the "All in order" check, a selected tile's
  check, the to-do count when it changes).
- Hover: colour and the `shadow-sm` of clickable cards only; the active nav icon turns filled.

**Navigation:** Back and Forward (`HistoryButtons`) sit top left: in the desktop title bar, at
the top left of the content area in a browser (never in the sidebar), in the phone top bar.
Bold arrows at `foreground/80`, a dead one at `/25`; both hidden (space kept) while there is
nowhere to go, as on the first page. A new page opens at its top; Back returns to
the scroll position the user left.

## Components

Use `frontend/src/components/ui/*` (shadcn) before writing new primitives.

- **Buttons:** 40px high (sm 36px; comfortable click targets), 12px radius, 14px/500. Variants: default (navy, hover `/80`), outline,
  secondary, ghost, destructive (soft red tint), link. Press nudges 1px down.
- **Inputs:** 40px, 1px `input` border, transparent bg (dark `input/30`), focus ring halo.
- **Cards:** white, ring hairline, 16px padding (12px `sm`). Section cards: title row + "See all →"
  link, then divided list.
- **List row:** category icon tile · title (truncate) + category · right-aligned reason (urgency
  colour) + amount · chevron. Hover `muted/40`.
- **Stat card:** neutral link card: big number, label with a small muted icon, hint. The number
  turns red or amber only when it is non-zero and calls for action.
- **Badges:** 20px pill, 12px/500.
- **Navigation:** 14px/500 rows with 16px Phosphor icon, `gap-3`, at least 40px high; active = `sidebar-accent` fill.
- **Agent:** opened from the ask bar or Ctrl K as a side sheet, not a route.
- **Feed card:** area or category tile (urgency dot for urgent/soon), title, detail sentence
  (the urgency in words), amount right-aligned, then its actions as buttons, under the text
  from `sm` and full width on a phone: the primary first, "See the document" (a preview, so no
  second "Open"), outline for the others, the dismiss ("All good", "Not needed") as a muted
  ghost at the end of the row.
- **Area tile** (My papers): card-like button, area icon tile + label, then its state in one
  or two lines of 12px text (red/amber text when it calls for action, muted otherwise);
  selected = 2px primary ring and a check. Grid: 2 columns on a phone, 3 from `sm`, 4 from `lg`.
- **Tabs** (My papers): text tabs on a hairline, the active one with a 2px primary underline,
  at least 44px high; the tab is kept in the address (`?tab=calendar`).
- **Question panel** (`components/questions.tsx`): a large dialog, one question per screen:
  the document page (`DocumentPage`, the place Binder read highlighted) on the left, the
  progress, question and full-width answer buttons on the right; stacked on a phone (document
  on top, answers below). Ends on "All in order ✓".
- **Viewer** (`components/viewer.tsx`): a page on a grey desk at the width of its frame, a
  toolbar below (zoom out, percentage = fit to width, zoom in, whole page, then the pager).
  Ctrl + wheel or pinch zooms around the cursor, double-click toggles 200 %, + / − / 0 keys;
  the mouse drags the page (not on a letter, whose text stays selectable).
- **Document page** (`DocumentPage`): the page image in the `Viewer`, on a white backing in
  both themes, the places Binder read outlined, the active field highlighted. Shared by the
  document page (fixed-height frame), the question panel and the feed's document preview (a
  large dialog, one chip per document).
- **Glossary term** (`components/glossary.tsx`): an administrative word with a dotted primary
  underline; a tap opens a popover with one sentence. `Glossed` marks the first occurrence of
  each term in a text (explanations, field labels, the papers to have, letter steps); never
  inside a button or a link. Terms and sentences: `i18n/messages/glossary.ts`.
- **Letter:** in its large dialog, an A4 sheet in the `Viewer` (laid out like the PDF, details
  in [brackets] marked amber); in the agent, the plain text with "Enlarge". Actions **Print**
  (primary) and **Send by post** (outline: numbered steps, then "I sent it"), the PDF download
  as ghost, **Cancel the letter** (destructive, right, after a confirmation; undoable).
  Leaving the editor with changes asks first. Print lays the text
  out like the PDF from a blank frame (the PDF route cannot be framed).
- **Undo:** every change ends with a Sonner toast carrying "Undo".
- **Toasts:** Sonner. Destructive confirmations: `ConfirmDialog`.

## Do's and Don'ts

### Do:
- **Do** use theme tokens (`bg-card`, `text-muted-foreground`, `bg-primary`) and add both light
  and `dark:` styles for any raw Tailwind hue.
- **Do** pair every urgency colour with a text label.
- **Do** keep text at 4.5:1: urgency text uses `-700` in light (`-600` amber/emerald fail on
  white), muted text stays `muted-foreground` without extra opacity.
- **Do** name every icon-only control (`aria-label`), expose state (`aria-pressed`,
  `aria-checked`, `aria-expanded`, `aria-current`) and give targets at least 24px (an `after:`
  inset widens a small one). Icons are hidden from screen readers app-wide (`IconContext`).
- **Do** announce what changes on its own (`role="status"`, mounted before it changes; errors
  `role="alert"`), and move focus to the next question or list when the control pressed goes away.
- **Do** use `PageHeader` for page titles and `CategoryIcon` for categories.
- **Do** show `Skeleton` while loading and a plain reassuring sentence when empty.

### Don't:
- **Don't** introduce new brand hues, gradients, or a second typeface.
- **Don't** add resting shadows or heavy borders; depth stays flat.
- **Don't** use solid red fills; destructive is a soft tint.
- **Don't** reach for generated-UI defaults: purple/violet for "AI", sparkle icons, gradient text,
  glassmorphism, glows, looping (pulsing, bouncing) decoration, monospace outside code, pastel-tinted
  card grids. The agent uses the navy brand like everything else.
- **Don't** hard-code UI strings; add EN and FR keys to `src/i18n/messages/*`.
- **Don't** restyle the phone scan page (`backend/src/binder/mobile/`) after the main app: it is a
  separate black, full-bleed camera UI with its own CSS variables.

---
name: Binder
description: AI administrative agent, 100% local
colors:
  primary: "oklch(0.28 0.07 262)"
  primary-dark: "oklch(0.585 0.15 259)"
  background: "oklch(0.985 0.003 250)"
  background-dark: "oklch(0.168 0.011 256)"
  foreground: "oklch(0.22 0.03 260)"
  foreground-dark: "oklch(0.935 0.006 256)"
  card: "oklch(1 0 0)"
  card-dark: "oklch(0.203 0.012 256)"
  sidebar: "oklch(0.975 0.004 250)"
  sidebar-dark: "oklch(0.148 0.011 256)"
  muted-foreground: "oklch(0.55 0.02 258)"
  accent: "oklch(0.95 0.018 255)"
  border: "oklch(0.925 0.008 255)"
  destructive: "oklch(0.6 0.2 25)"
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

## Overview

**Creative North Star: "The Personal Secretary"**

Binder greets you, tells you what needs your attention today, and keeps everything else quietly in
order. The interface is an Operate surface: calm, dense enough to scan, never decorative. Ink navy
carries the brand; colour elsewhere is a signal (urgency, category), never ornament. Dark mode is a
"night vault": ink surfaces with a faint blue cast, depth by lightness steps.

**Key Characteristics:**
- Navy brand, cool near-white surfaces, one accent family.
- Colour only for meaning: urgency (red/amber/emerald) and category tones.
- Flat surfaces, hairline rings and borders, generous 12px-based radii.
- Plain sentences as headings and hints; no status badges or pulsing dots.

## Colors

### Primary
- **Ink Navy** (`primary`): primary buttons, logo tile, active nav text, links. Turns **Periwinkle**
  (`primary-dark`) in dark mode so buttons keep their weight.

### Neutral
- **Cool Paper** (`background`) page; **White** (`card`) cards and popovers; **Sidebar Mist**
  (`sidebar`) navigation; **Ink** (`foreground`) text; **Slate** (`muted-foreground`) secondary
  text; **Haze** (`accent`) hover and active fills; hairline `border`.
- Dark: surfaces lighten as they come forward: sidebar < background < card < popover. Borders are
  white at 6-11% alpha.

### Signals (Tailwind palette, not tokens)
- Urgency (`urgencyStyles`, `lib/format.ts`): late/urgent red, soon amber, later emerald; as dot,
  pill (`-50` bg / `-700` text; dark `-500/15` bg / `-300` text) or text.
- Categories (`CATEGORY_STYLE`, `lib/categories.tsx`): one hue + Phosphor icon per category, pastel
  tile in light, `/15` tint in dark.
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

## Layout

Fixed 240px sidebar (`md`+): "Ask Binder" first (opens the agent, Ctrl K anywhere), then Today,
Prepare (every letter, file and life event Binder handles, and what it is following) and Documents
(search across everything), then "Your life" with the seven life areas (with a count of cards that
need attention), and History / Trash / Settings links pinned bottom; below `md` it becomes a
horizontal scrolling tab strip led by "Ask Binder". Today opens on the agent's composer (a sentence,
examples, attach); every other page has the ask bar fixed at the bottom. Content in a centred
full width (no centred column), `px-4 py-6` mobile, `px-8 py-8` desktop. Page header then content,
`mb-7`. Today: greeting and one-sentence summary, the agent composer, then "To do", "Binder has a
question" and "Also worth a look"; side column "In progress" (journeys, letters to send or awaiting
an answer) and "Coming up". Area pages: main column + 24-28rem side column from `xl` (coming up,
recurring bills, the area's "Prepare" shortcuts). Prepare: tiles in a 2-3 column grid by section,
"In progress" on the side when there is any. Settings: one section per row, title and description on the
left (16-20rem), cards on the right.
Grids: `sm:grid-cols-3` stats, `lg:grid-cols-2` sections, gaps 16-24px. Lists are full-width rows
(`px-5 py-3`) divided by hairlines inside a card.

## Elevation & Depth

Flat. Cards use a 1px ring (`foreground/10`) or border, no resting shadow. `shadow-sm` appears only
on hover of clickable cards. Dark mode conveys depth by surface lightness, not shadow. Focus is a
3px `ring/50` halo.

## Shapes

`--radius` 0.75rem drives the scale (sm 0.6x … 4xl 2.6x). Buttons, inputs, nav items, icon tiles:
`rounded-lg` (12px). Cards: `rounded-xl` (~17px). Badges and pills: fully round. Status dots: 8px
circles with a 4px soft ring.

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
- **Agent:** opened from the nav or the ask bar as a side sheet, not a route.
- **Feed card:** area or category tile (urgency dot for urgent/soon), title, detail sentence
  (the urgency in words), amount right-aligned, then its actions as buttons: one primary,
  outline for the others, ghost for dismiss.
- **Question panel** (`components/questions.tsx`): a large dialog, one question per screen:
  the document page (`DocumentPage`, the place Binder read highlighted) on the left, the
  progress, question and full-width answer buttons on the right; stacked on a phone (document
  on top, answers below). Ends on "All in order ✓".
- **Undo:** every change ends with a Sonner toast carrying "Undo".
- **Toasts:** Sonner. Destructive confirmations: `ConfirmDialog`.

## Do's and Don'ts

### Do:
- **Do** use theme tokens (`bg-card`, `text-muted-foreground`, `bg-primary`) and add both light
  and `dark:` styles for any raw Tailwind hue.
- **Do** pair every urgency colour with a text label.
- **Do** use `PageHeader` for page titles and `CategoryIcon` for categories.
- **Do** show `Skeleton` while loading and a plain reassuring sentence when empty.

### Don't:
- **Don't** introduce new brand hues, gradients, or a second typeface.
- **Don't** add resting shadows or heavy borders; depth stays flat.
- **Don't** use solid red fills; destructive is a soft tint.
- **Don't** reach for generated-UI defaults: purple/violet for "AI", sparkle icons, gradient text,
  glassmorphism, glows, pulsing or bouncing decoration, monospace outside code, pastel-tinted
  card grids. The agent uses the navy brand like everything else.
- **Don't** hard-code UI strings; add EN and FR keys to `src/i18n/messages/*`.
- **Don't** restyle the phone scan page (`backend/src/binder/mobile/`) after the main app: it is a
  separate black, full-bleed camera UI with its own CSS variables.

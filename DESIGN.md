# DESIGN.md — HawaKhata design system

Single source of truth for the visual design. Stitch reads it to keep generated screens consistent;
the build translates it into CSS variables in `static/css/app.css`. Change tokens here first.

## 1. Personality
Calm, trustworthy, quietly modern — a **passbook**, not an alarm siren. Think "good banking app meets
weather app". Clear numbers, generous whitespace, one accent colour, no stock photos, no illustrations
beyond simple line icons. Serious about health, never scary.

## 2. Colour tokens (light)
| Token | Hex | Use |
|---|---|---|
| `--bg` | `#F7F6F2` | page background (warm paper) |
| `--surface` | `#FFFFFF` | cards, sheets |
| `--surface-2` | `#EFEDE6` | subtle fills, ledger zebra rows |
| `--ink` | `#1A1D21` | primary text |
| `--muted` | `#5B6168` | secondary text (≥ 4.5:1 on bg and surface) |
| `--line` | `#DAD7CE` | hairlines, borders |
| `--accent` | `#0F6E66` | primary actions, active nav, links |
| `--accent-ink` | `#FFFFFF` | text on accent |
| `--debit` | `#B4233C` | inhaled / over budget (always with ▼ and the word) |
| `--saved` | `#167A3A` | saved / under budget (always with ▲ and the word) |
| `--warn` | `#A55A00` | caution notices |
| `--focus` | `#1D4ED8` | 3px focus ring |

Dark theme: `--bg #111417`, `--surface #1A1F24`, `--surface-2 #222830`, `--ink #EEF1F4`,
`--muted #A7B0BA`, `--line #2E353D`, `--accent #3FB8AC`, `--debit #FF7A8A`, `--saved #5FD08A`.

### AQI category scale (India NAQI) — colour is NEVER the only signal
Each chip = icon + category word + number. Good `#2E7D32` · Satisfactory `#7CB342` · Moderate `#C9A400`
(dark text) · Poor `#E07B00` (dark text) · Very Poor `#C62828` · Severe `#6A1B4D`.
Icons: Good ☺-style smile, Satisfactory leaf, Moderate cloud, Poor haze lines, Very Poor mask, Severe
warning triangle — simple 24px stroke SVGs in one sprite.

## 3. Typography
System stack: `system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", "Noto Sans Devanagari",
sans-serif`. No web fonts. `font-variant-numeric: tabular-nums` for all figures.
Scale (rem): display 2.25/700 (hero numbers) · h1 1.75/700 · h2 1.375/650 · h3 1.125/600 ·
body 1/400 (line-height 1.55) · small 0.875/500. Hindi gets +0.0625rem and line-height 1.7.

## 4. Space, shape, depth
Spacing scale 4/8/12/16/24/32/48 px. Radius: cards 16px, chips 999px, inputs 12px.
Shadow: `0 1px 2px rgb(0 0 0 / .06), 0 4px 16px rgb(0 0 0 / .05)`. Max content width 1120px.
Breakpoints: ≤ 599 mobile (single column, bottom nav) · 600–899 tablet · ≥ 900 desktop (left rail,
two-column content).

## 5. Components
- **Top bar:** wordmark "HawaKhata" (ink, 700) + small "हवा खाता" + city button + AQI chip + language toggle.
- **Nav:** mobile bottom bar (Today · Plan · Home air · Swaps), desktop left rail; "Ask" is a floating
  action button (bottom-right) opening a chat sheet.
- **Balance row (signature component):** member name + age tag · horizontal bar showing debit vs budget
  (budget marker line) · pill "19× over budget ▼" or "Within budget ▲" · chevron → "Why this number?".
- **Move card:** title ("Shift Dadi's walk to 3 PM"), impact line ("▲ saves 1,240 µg"), member avatars
  (initial circles), primary button "Add to plan".
- **Clean-hours strip:** 24 small columns (hour bars) coloured by AQI category, best window outlined with
  label "Cleanest: 2–5 PM".
- **Chart card:** inline SVG line/area, labelled axes, "Show as table" text button.
- **Toggle row:** label + description + switch (`button[aria-pressed]`).
- **Slider row:** label + `<input type=range>` + live `<output>`.
- **Chat sheet:** messages, number chips (tap → explanation), quick-reply chips, input + send.
- **Story overlay:** bottom caption card "Step 2 of 7", caption text, Back / Next, Esc to exit;
  highlighted target gets a 3px accent outline (no dimming animations if reduced motion).
- **States:** skeleton shimmer (static if reduced motion), empty state with one clear action, error card
  with retry, "Demo data" banner when `data_mode = fixture`.

## 6. Motion
120–200ms ease-out for state changes; number count-up ≤ 400ms; no parallax, no autoplay loops.
All motion disabled under `prefers-reduced-motion: reduce`.

## 7. Voice
Short, warm, specific. Say "fine dust (PM2.5)" the first time. Numbers always with a unit and a
comparison ("19× her daily budget"). Never blame; always offer the next move.

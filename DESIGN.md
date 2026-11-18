# DESIGN.md — HawaKhata design system

Single source of truth for the visual design. Translated into CSS variables in `static/css/app.css`.

## 1. Personality
Calm, trustworthy, quietly modern — an air passbook. Clear numbers, generous whitespace, one accent colour, simple line icons. Serious about health, never alarmist.

## 2. Colour Tokens (Light)
| Token | Hex | Use |
|---|---|---|
| `--bg` | `#F7F6F2` | page background (warm paper) |
| `--surface` | `#FFFFFF` | cards, sheets |
| `--surface-2` | `#EFEDE6` | subtle fills, zebra rows |
| `--ink` | `#1A1D21` | primary text |
| `--muted` | `#5B6168` | secondary text (≥ 4.5:1 contrast) |
| `--line` | `#DAD7CE` | borders, dividers |
| `--accent` | `#0F6E66` | primary actions, links |
| `--accent-ink` | `#FFFFFF` | text on accent |
| `--debit` | `#B4233C` | inhaled / over budget (with ▼) |
| `--saved` | `#167A3A` | saved / under budget (with ▲) |
| `--warn` | `#A55A00` | caution notices |
| `--focus` | `#1D4ED8` | 3px focus ring |

Dark theme: `--bg #111417`, `--surface #1A1F24`, `--surface-2 #222830`, `--ink #EEF1F4`, `--muted #A7B0BA`, `--line #2E353D`, `--accent #3FB8AC`, `--debit #FF7A8A`, `--saved #5FD08A`.

### AQI Category Scale (India NAQI) — Colour is never the only signal
Each chip: icon + category text + value. Good `#2E7D32` · Satisfactory `#7CB342` · Moderate `#C9A400` (dark text) · Poor `#E07B00` (dark text) · Very Poor `#C62828` · Severe `#6A1B4D`.

## 3. Typography
System stack: `system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", "Noto Sans Devanagari", sans-serif`. `font-variant-numeric: tabular-nums` for all figures.
Scale: display 2.25rem/700, h1 1.75rem/700, h2 1.375rem/650, h3 1.125rem/600, body 1rem/400 (line-height 1.55), small 0.875rem/500. Hindi gets +0.0625rem and line-height 1.7.

## 4. Space, Shape, Depth
Scale: 4/8/12/16/24/32/48 px. Radius: cards 16px, chips 999px, inputs 12px.
Shadow: `0 1px 2px rgb(0 0 0 / .06), 0 4px 16px rgb(0 0 0 / .05)`. Max width 1120px.
Breakpoints: ≤ 599 mobile (bottom nav) · 600–899 tablet · ≥ 900 desktop (left rail).

## 5. Components
- **Top bar:** Brand mark + Hindi title + city modal button + AQI chip + language toggle.
- **Nav:** Mobile bottom bar (Today, Plan, Home air, Swaps), desktop left rail; floating Ask button.
- **Balance row:** Member name + age · horizontal bar (debit vs budget) · pill status · "Why this number?".
- **Hours strip:** 24 column cells coloured by NAQI category, clean window highlighted.
- **Story overlay:** Guided tour banner with step indicator, caption, Back/Next controls.
- **Accessibility:** Reduced motion disables transitions; all interactive elements have 44x44px minimum touch targets and visible focus indicators.

# DESIGN.md — HawaKhata design system

Single source of truth for visual design, matching CSS variables in `static/css/app.css`.

## 1. Personality
Calm, trustworthy, modern air passbook. Clear numbers, generous whitespace, single accent colour, simple line icons. Serious about health, never alarmist.

## 2. Colour Tokens (Light)
| Token | Hex | Use |
|---|---|---|
| `--bg` | `#F7F6F2` | background (warm paper) |
| `--surface` | `#FFFFFF` | cards, sheets |
| `--surface-2` | `#EFEDE6` | subtle fills |
| `--ink` | `#1A1D21` | primary text |
| `--muted` | `#5B6168` | secondary text |
| `--line` | `#DAD7CE` | borders, dividers |
| `--accent` | `#0F6E66` | primary actions |
| `--accent-ink` | `#FFFFFF` | text on accent |
| `--debit` | `#B4233C` | over budget (▼) |
| `--saved` | `#167A3A` | under budget (▲) |
| `--warn` | `#A55A00` | caution notices |
| `--focus` | `#1D4ED8` | 3px focus ring |

Dark theme: `--bg #111417`, `--surface #1A1F24`, `--surface-2 #222830`, `--ink #EEF1F4`, `--muted #A7B0BA`, `--line #2E353D`, `--accent #3FB8AC`, `--debit #FF7A8A`, `--saved #5FD08A`.

### AQI Scale (India NAQI) — Colour is never the only signal
Good `#2E7D32` · Satisfactory `#7CB342` · Moderate `#C9A400` · Poor `#E07B00` · Very Poor `#C62828` · Severe `#6A1B4D`.

## 3. Typography & Depth
- Stack: `system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", "Noto Sans Devanagari", sans-serif`. Tabular nums for all numbers.
- Scale: 4/8/12/16/24/32/48 px. Radius: cards 16px, chips 999px, inputs 12px.
- Breakpoints: ≤ 599 mobile (bottom nav) · 600–899 tablet · ≥ 900 desktop (left rail).

## 4. Components
- **Top bar:** Brand mark + Hindi title + city modal button + AQI chip + language toggle.
- **Nav:** Mobile bottom bar (Today, Plan, Home air, Swaps), desktop left rail; floating Ask button.
- **Passbook card:** Member name + age · horizontal bar (debit vs budget) · pill status · "Why this number?".
- **Hours strip:** 24 column cells coloured by NAQI category, clean window highlighted.
- **Story overlay:** Guided tour banner with step indicator, caption, Back/Next controls.

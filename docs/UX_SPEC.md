# UX_SPEC — HawaKhata

## Usability Targets
- First insight ≤ 60s (or 1 tap with demo family).
- Any number → explanation in ≤ 1 tap ("Why this number?").
- One question per screen; one primary action per card.
- 360px mobile to desktop; WCAG 2.2 AA; English & Hindi.

## Information Architecture
| Screen | Question | Primary action |
|---|---|---|
| Onboarding | Who/where? | Continue / Demo family |
| **Today** | Family air balance? | Add move to plan |
| **Plan** | When to go out? | Apply better plan |
| **Home air** | Clean indoor air? | Toggle hack |
| **Swaps** | Alternatives? | Select swap / Mohalla size |
| **Ask** | Anything else? | Send question |
| **How it works** | Trust numbers? | View formulas & sources |

Navigation: mobile bottom bar + Ask button; desktop top navigation bar with header Ask CTA; Light/Dark toggle.

## Screen Specifications
- **Today screen:** Top bar (City, NAQI chip, demo badge); 4-card hero grid (Debit, WHO Budget, Net Balance, Cigarettes); Passbook member list with budget bars; cleanest window; shift banner.
- **Plan screen:** 24h hours strip coloured by NAQI; recommended schedule shifts with exposure savings; "Add to plan".
- **Home air screen:** Baseline vs intervention PM2.5; CADR calculator (5 ACH target); ranked indoor hacks.
- **Swaps screen:** Household emission cards; Mohalla slider (1–500 homes) with community emissions avoided.
- **Ask drawer:** Slide-over with polite live region; message history; AI status; emergency medical banner.
- **Story mode:** `/?story=ncr|chd`: deterministic 5-step guided tour with step indicator, overlay caption, keyboard navigation.

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
| **Today** (home) | Family air balance & next move? | Add move to plan |
| **Plan** | When to go out? | Apply better plan |
| **Home air** | Clean indoor air? | Toggle hack |
| **Swaps** | Neighbourhood alternatives? | Select swap / Mohalla size |
| **Ask** (sheet) | Anything else? | Send question |
| **How it works** | Trust numbers? | View formulas & sources |

Navigation: mobile bottom bar + Ask button; desktop left rail; top bar settings/help.

## Screen Specifications
- **Today screen:** Top bar (City, NAQI chip, demo fixture badge); 4-card hero grid (Debit, WHO Budget, Net Balance, Cigarette Equiv); Family passbook member list with budget bars; 24h cleanest window highlight; proactive shift banner.
- **Plan screen:** 24h interactive hours strip coloured by NAQI category; recommended schedule shifts with quantified µg exposure savings; "Add to plan" action.
- **Home air screen:** Room selector; baseline vs intervention PM2.5; AHAM CADR sizing calculator (5 ACH target); ranked indoor hacks with interactive toggle states.
- **Swaps screen:** Household emission reduction cards; Mohalla multiplier slider (1–500 homes) with collective community emissions avoided.
- **Ask sheet:** Slide-over drawer with polite live region; message history; AI state handling (thinking, unavailable, fallback); emergency medical banner on red-flag symptoms.
- **Story mode:** `/?story=ncr|chd`: deterministic 5-step guided tour with step indicator, overlay caption, and keyboard navigation (Back/Next/Esc).

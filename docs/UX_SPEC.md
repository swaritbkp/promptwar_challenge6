# UX_SPEC — HawaKhata

## Usability targets
- First insight ≤ 60s (or 1 tap with demo family).
- Any number → explanation in ≤ 1 tap ("Why this number?").
- One question per screen; one primary action per card.
- 360px mobile to desktop; WCAG 2.2 AA; English & Hindi.

## Information architecture
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

## Onboarding (≤ 60s, skippable)
1. **Location:** City chips (Delhi, Gurugram, Noida, Ghaziabad, Faridabad, Chandigarh, Mohali, Panchkula) or search (~1 km rounded).
2. **Family:** Adult / Child / Elder chips + optional lung/heart sensitivity checkbox.
3. **Home:** Purifier (room + size), heating (none/electric/angithi/wood), cooking, commute mode.
Footer on every step: "Try a demo family".

## Today screen
1. Top bar: City, AQI chip (color, label, value), fixture badge if demo data.
2. **Family air balance:** Per-member balance rows (overspent first).
3. **3 moves for today:** Ranked by µg saved. One sentence + savings + "Add to plan".
4. **Cleanest hours:** 24h strip highlighting best clean window.
5. Alerts for sensitive members & severe hours + diurnal context.
6. Auto re-plan banner when forecast shifts.

## Plan screen
Stacked 24h timelines: "Usual" vs "Better" with category colors, savings badge, and robust P90 uncertainty note.
Button: "Use the better plan" updates profile and Today screen.

## Home air screen
Room selector → outdoor vs indoor timeline → interactive toggles: windows, purifier CADR, cooking, heating → 250ms debounced recompute → ranked hacks list + purifier sizing verdict.

## Swaps screen
Relevant swap cards: before vs after, Δ breathe avoided per member, Δ emit less (kg CO₂, g PM2.5).
**Mohalla multiplier:** households slider (1–1000) × adoption rate → collective community impact.

## Ask sheet
Localised greeting + suggestions. Number chips tap to explanation; follow-up chips. Symptom red flags trigger prominent medical emergency banner. Input hint: "Do not share phone numbers, ID numbers or addresses."

| AI state | Meaning | User sees |
|---|---|---|
| Thinking | Generating | Progress dots; Send disabled |
| Unavailable | Quota/Down | Fallback advice + screen links |
| Doesn't know | Out of scope | Refusal + suggestion chips |
| Answered | Normal | textContent plain text, number chips |

## Story mode
`/?story=ncr` or `/?story=chd`: loads demo family, fixture air data, fixed clock. 7-step tour (Today → Why number → Plan → Home air → Swaps → Ask HI → How it works). Keyboard: →/Enter next, ← back, Esc exit. Real API/engine endpoints power all figures.

## Journeys & States
- First visit: Onboarding or 1-tap demo family. Missing location falls back cleanly to city chips.
- Daily check: Today shows cached forecast, moves, balances. Degrades to fixture on upstream failure.
- Ask: Grounded answer; quota exhaustion gives structured 429 and fallback narration.
- Skeletons on loading; error messages follow standard error contract; tooltips use `<details>`.

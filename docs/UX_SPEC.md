# UX_SPEC — HawaKhata

## Usability targets
- First useful insight in **≤ 60 seconds** from opening the app (or 1 tap with a demo family).
- Any number → its explanation in **≤ 1 tap** ("Why this number?").
- Every screen answers one question; one primary action per card.
- Works one-handed on a 360px phone; fully usable by keyboard and screen reader; English and Hindi.

## Information architecture
| Screen | Question it answers | Primary action |
|---|---|---|
| Onboarding (3 steps) | "Who are we and where?" | Continue / Try a demo family |
| **Today** (home) | "How is my family's air account today, and what should we do?" | Add a move to today's plan |
| **Plan** | "When should each of us go out?" | Apply the better plan |
| **Home air** | "How do I make the air inside cleaner?" | Turn on a hack and see the effect |
| **Swaps** | "What can we change that also helps the neighbourhood?" | Pick a swap / set Mohalla size |
| **Ask** (sheet) | "Anything else?" | Send a question |
| **How it works** | "Can I trust these numbers?" | Read sources |

Navigation: mobile bottom bar (Today · Plan · Home air · Swaps) + Ask floating button; desktop left rail.
"How it works" and language/city settings live in the top bar menu.

## Onboarding (≤ 60 s, all skippable, everything editable later)
1. **Where do you live?** "Use my location" or city chips (Delhi, Gurugram, Noida, Ghaziabad, Faridabad,
   Chandigarh, Mohali, Panchkula) + search. Coordinates are rounded before use (say so in one line).
2. **Who's at home?** Add-member chips: Adult · Child · Elder → asks only age band + optional
   "sensitive lungs/heart" checkbox (explained: stays on this device). Optional nickname.
3. **Your home in 5 taps:** air purifier (which room, size S/M/L → CADR preset), heating
   (none/electric/angithi/wood), incense daily?, mosquito coil?, main commute (car/two-wheeler/metro-bus/walk).
Footer link on every step: **"Just show me — try a demo family"** (Delhi NCR or Chandigarh).

## Today screen (the hero)
1. Top bar: city · AQI chip (icon + word + number) · "Demo data" badge if fixture.
2. **Family air balance** card: one Balance row per member (sorted: most overspent first).
3. **3 moves for today** (from planner + indoor hacks + swaps ranked by µg saved for the family).
   Each: one sentence + "▲ saves X µg" + "Add to plan".
4. **Cleanest hours** strip for the next 24h with the best window labelled.
5. Alerts (sensitive members, severe hours) + "What changed since yesterday" one-liner.
6. Re-plan banner when the forecast shifts: "Tomorrow got worse at 7 AM — we moved Riya's play to 3 PM."

## Plan screen
Two stacked timelines per member: "Usual" vs "Better" (hour blocks coloured by category), savings badge,
uncertainty note ("even if the forecast is off, this stays better 9 times out of 10" — from P90 logic).
Button: "Use the better plan" (saves to profile; Today updates).

## Home air screen
Room picker (chips) → chart: outdoor vs indoor today → toggles: windows (hour range), purifier on/off +
size, cooking (tadka/frying times), incense, mosquito coil, heating → live recompute (debounced 250ms) →
"Best 3 hacks for this room" ranked list with µg saved → purifier sizing verdict.

## Swaps screen
Swap cards (only those relevant to the profile first). Each: before → after, ▲ breathe saved per member,
▼ emitted less (kg CO₂, g PM2.5) per week/month toggle, ranges shown as "about 1.2–1.8 kg".
**Mohalla multiplier** card: households slider (1–1000), participation slider → collective impact.

## Ask sheet
Greeting + 4 suggestion chips (localised). Answers show number chips (tap → explanation) and quick-reply
chips for follow-ups. Red-flag symptom messages show a prominent "Seek medical care now" card first.
Hint under the input: "Please don't share phone numbers, ID numbers or addresses."

| AI state | What it means | What the user sees |
|---|---|---|
| Thinking | Waiting for Gemini (can take seconds) | "Checking the air for your family…" with progress dots; Send disabled (no double submit) |
| Unavailable | Gemini down, slow, or the daily limit reached | "The assistant is resting — your passbook, plan, home air and swaps still work." + links to those screens |
| Doesn't know | The assistant correctly refused to guess | "I can't answer that from your air data. Try: …" + 2 suggestion chips |
| Answered | Normal reply | Text (inserted as plain text), number chips, optional follow-up chips |

## Story mode (for demos and first-time users)
`/?story=ncr` or `/?story=chd`: loads a demo family + fixture data + fixed clock; a caption card walks
through 7 steps (Today → Why this number → Plan → Home air → Swaps + Mohalla → Ask in Hindi → How it
works). Keyboard: → / Enter next, ← back, Esc exit. Steps defined in `data/story.v1.json`; every number
on screen still comes from the real API and engine.

## Privacy controls
Settings → "Clear my data" removes the saved profile from this device (confirmation step, then a
success message). First-run note: "Your family details stay on this device."

## Main journeys (including failure paths)
1. **First visit:** open → onboarding (or "try a demo family") → Today shows balances. If location
   permission is denied → city chips stay available; nothing breaks.
2. **Daily check:** open → Today (forecast fetched; cached) → tap a move → "Add to plan" → Plan shows
   the change. If live data fails → fixture banner + last cached data, never a blank screen.
3. **Ask:** open Ask → question → grounded answer. If quota reached → "Unavailable" state; if the
   question is out of scope → "Doesn't know" state.

## States & microcopy
Loading: skeletons. Empty: one sentence + one button. Error: what happened + "Try again" (uses error
contract message). Offline keys: "Showing demo air data — add keys for live data" (fixture banner).
Units: "µg (micrograms) of fine dust" on first use per screen; tooltips are `<details>`, not hover.

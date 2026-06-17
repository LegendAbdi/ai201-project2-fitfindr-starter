# FitFindr — Demo Recording Script (3–5 min)

Start the app first: `python app.py` → open the URL it prints (usually
http://localhost:7860). Keep a terminal visible too — you'll use it for the
`create_fit_card` failure that the UI can't trigger.

---

## Part 1 — Complete interaction, all 3 tools (~90 sec)

**Wardrobe radio:** `Example wardrobe`
**Prompt to type:**

```
vintage graphic tee under $30, size M
```

Narrate as the three panels fill, pointing to each one:

- **🛍️ Top listing found** → *"This is Tool 1, `search_listings`. It parsed
  `description='vintage graphic tee'`, `size='M'`, `max_price=30` out of my sentence,
  scored every listing by keyword overlap, and returned the top match — the Y2K Baby
  Tee, $18 on depop."*
- **👗 Outfit idea** → *"This is Tool 2, `suggest_outfit`. It took that exact listing
  plus my wardrobe and called the LLM — notice it names real pieces I own: my baggy
  straight-leg jeans and chunky white sneakers."*
- **✨ Your fit card** → *"This is Tool 3, `create_fit_card`. It turned the outfit
  into a post-ready caption."*

## Part 2 — Show state passing between tools (~45 sec)

Stay on the same result and narrate the **visible chain**:

> *"Watch how state flows. The listing panel says **Y2K Baby Tee, $18, depop**. The
> fit card panel mentions that **same item, same $18, same depop** — and the **same
> pieces** the outfit panel named. Nothing was re-typed or hardcoded between steps:
> the agent stored the chosen listing in one `session` dict and passed that exact
> object into the next tool."*

(Optional, stronger proof — run in the terminal and show the `True`s:)

```bash
python -c "
import agent; from agent import run_agent
from utils.data_loader import get_example_wardrobe
calls={}
_s=agent.suggest_outfit; _c=agent.create_fit_card
agent.suggest_outfit=lambda i,w: calls.__setitem__('si',i) or _s(i,w)
agent.create_fit_card=lambda o,i: (calls.__setitem__('co',o),calls.__setitem__('ci',i)) and _c(o,i) or _c(o,i)
s=run_agent('vintage graphic tee under \$30 size m', get_example_wardrobe())
print('selected_item passed to suggest_outfit:', s['selected_item'] is calls['si'])
print('selected_item passed to create_fit_card:', s['selected_item'] is calls['ci'])
print('outfit passed to create_fit_card:', s['outfit_suggestion'] is calls['co'])
"
```

## Part 3 — Error handling: no results (~45 sec)

**Wardrobe radio:** `Example wardrobe`
**Prompt to type:**

```
designer ballgown size XXS under $5
```

Narrate:

> *"Here's a query nothing can match. `search_listings` returns an empty list, so the
> agent **branches** — it does NOT call the outfit or fit-card tools. Instead it
> tells me exactly what failed and what to change: 'No matches for designer ballgown
> under \$5 in size XXS — try raising your budget, dropping the size filter, or
> broader keywords.' The other two panels stay empty."*

This is the moment that proves the agent decides what to do based on tool output,
rather than always running the same sequence.

---

## Optional extra failure modes (if you have time)

**Empty wardrobe (graceful, not a crash).**
Wardrobe radio: `Empty wardrobe (new user)`, same tee prompt as Part 1.
Narrate: *"With no wardrobe, `suggest_outfit` doesn't crash — it returns general
styling advice instead of naming specific pieces."*

**Empty-outfit guard on `create_fit_card`** (UI can't reach this — show in terminal):

```bash
python -c "from tools import search_listings, create_fit_card; print(create_fit_card('', search_listings('vintage graphic tee', None, 50)[0]))"
```

Narrate: *"If `create_fit_card` is ever handed an empty outfit, it returns a
descriptive error string instead of raising."*
```

---

## Quick prompt cheat-sheet

| Goal | Wardrobe | Prompt |
|------|----------|--------|
| All 3 tools, happy path | Example wardrobe | `vintage graphic tee under $30, size M` |
| Alt happy path | Example wardrobe | `90s track jacket in size M` |
| Error: no results | Example wardrobe | `designer ballgown size XXS under $5` |
| Failure mode: empty wardrobe | Empty wardrobe (new user) | `vintage graphic tee under $30, size M` |
| Failure mode: empty outfit | (terminal only — see above) | — |

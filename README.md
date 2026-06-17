# FitFindr 🛍️

FitFindr is a tool-using agent that helps a thrift shopper go from *"I want X"* to
*"here's a real secondhand listing, here's how to wear it with clothes you already
own, and here's a caption to post it."* It chains three tools through a planning
loop that **decides what to do next based on what each tool returns** — most
importantly, it refuses to style or caption an item that doesn't exist.

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Run it

```bash
python app.py
```

Open the URL printed in your terminal (usually <http://localhost:7860>, but check
the output — the port can differ). Type what you're looking for, pick a wardrobe,
and hit **Find it**. The three panels show the matched listing, an outfit idea, and
a ready-to-post fit card.

You can also drive the agent from the command line:

```bash
python agent.py        # runs a happy-path query and a no-results query
pytest tests/          # runs all tool + failure-mode tests
pytest tests/ -m "not live"   # same, but skips the one real-API test (offline)
```

---

## Tool Inventory

All three tools live in [`tools.py`](tools.py) and are independently callable and
tested. Tools never call each other — the planning loop in [`agent.py`](agent.py)
threads state between them.

### 1. `search_listings(description, size, max_price)`

| | |
|---|---|
| **Inputs** | `description: str` (keywords, e.g. `"vintage graphic tee"`), `size: str \| None` (filter, case-insensitive substring — `"M"` matches `"S/M"`), `max_price: float \| None` (inclusive ceiling) |
| **Output** | `list[dict]` — matching listings sorted by relevance, best first. `[]` if nothing matches. |
| **Purpose** | Find secondhand listings matching the shopper's request. Pure Python (no LLM): filter by price/size, score each listing by keyword overlap against `title` + `description` + `style_tags`, drop zero-score listings, sort by score. |

### 2. `suggest_outfit(new_item, wardrobe)`

| | |
|---|---|
| **Inputs** | `new_item: dict` (a listing dict — the item being considered), `wardrobe: dict` (has an `items` key holding wardrobe-item dicts; may be empty) |
| **Output** | `str` — 1–2 outfit suggestions. Never empty. |
| **Purpose** | Style the found item. Calls Groq (`llama-3.3-70b-versatile`). With a filled wardrobe it names *real pieces the user owns* ("pair it with your baggy straight-leg jeans and chunky white sneakers"); with an empty wardrobe it gives general styling advice instead. |

### 3. `create_fit_card(outfit, new_item)`

| | |
|---|---|
| **Inputs** | `outfit: str` (the suggestion from `suggest_outfit`), `new_item: dict` (the listing dict) |
| **Output** | `str` — a 2–4 sentence Instagram/TikTok caption, or a descriptive error string if `outfit` is empty. |
| **Purpose** | Turn the find + outfit into a casual, shareable caption. Calls Groq at a **higher temperature (1.0)** so captions vary between runs. Mentions the item name, price, and platform once each. |

---

## How the Planning Loop Works (what the agent *decides*)

The loop in `run_agent(query, wardrobe)` is **not** a fixed "call all three tools"
script. It's a sequence with one decision point that can end the run early. State
lives in a single `session` dict that every step reads from and writes to.

```
query → parse → search → [empty? → STOP with error] → select top → suggest → fit card → done
```

1. **Initialize.** `_new_session()` builds the `session` dict (all output fields
   start `None`).

2. **Parse the query** (`_parse_query`, pure regex — no LLM). It pulls three things
   out of free text:
   - `max_price`: a `$NN` / `under NN` / `below NN` pattern → `float`.
   - `size`: a `size X` token (S/M/L/XL or a number) → `str`.
   - `description`: everything left after stripping those phrases and filler words.

   **Decision:** if no usable `description` survives parsing (e.g. the user typed
   only `"under $30 size M"`), the agent sets `session["error"]` and **returns
   immediately** — it never searches with empty keywords.

3. **Search.** Calls `search_listings(**session["parsed"])`.

   **This is the key decision point.** The agent branches on the *result*, not on a
   fixed plan:
   - **Empty list →** set `session["error"]` to a message that names which filter to
     loosen, then **return early.** `suggest_outfit` and `create_fit_card` are
     *never called.* This is what makes the agent behave differently on different
     inputs.
   - **Non-empty →** set `session["selected_item"] = search_results[0]` (top-ranked)
     and continue.

4. **Suggest outfit.** Calls `suggest_outfit(selected_item, wardrobe)`. An empty
   wardrobe is **not** an error here — the tool returns general advice, so the run
   still completes. If the LLM call itself raises, the loop catches it, sets
   `session["error"]`, and stops before the fit card.

5. **Create fit card.** Calls `create_fit_card(outfit_suggestion, selected_item)`
   and stores the caption.

6. **Return** the session.

**Termination:** there's no iteration or re-planning. Each stage runs at most once.
The run ends either when `fit_card` is set (success) or at the first stage that sets
`error` (early exit). The caller checks `session["error"]` first — if it's set, the
later output fields are `None`.

---

## State Management

A single `session` dict (built by `_new_session()`) is the source of truth for one
interaction. Tools don't talk to each other; the loop reads each tool's input out of
`session` and writes its output back in. The *exact same objects* are threaded
through — verified with identity (`is`) checks, not just equality, so there's no
re-prompting or hardcoded hand-off between steps.

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | `_new_session` | parse step |
| `parsed` (`description`, `size`, `max_price`) | parse step | `search_listings` |
| `search_results` | `search_listings` | empty-check branch, selection |
| `selected_item` | selection (`search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | caller / `_new_session` | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | final output |
| `error` | any step that exits early | caller (checked first) |

State exists only for the duration of one `run_agent` call — there's no cross-session
persistence. [`app.py`](app.py)'s `handle_query()` calls `run_agent()`, then maps the
finished session onto the three UI panels (or the error onto the first panel).

---

## Error Handling (per tool, with a real example)

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | No listing matches the query | Tool returns `[]` (never raises). The loop turns that into a specific, actionable error and stops before the LLM tools. |
| `suggest_outfit` | Wardrobe is empty | **Not** an error — the tool detects `wardrobe["items"] == []` and returns general styling advice, so the run still produces a fit card. (If the *LLM call* raises, the loop catches it, sets `error`, and stops.) |
| `create_fit_card` | `outfit` is empty / whitespace / `None` | Tool guards the input and returns a descriptive error string instead of crashing or inventing a caption. |

**Concrete example from testing — the no-results path.** Running the impossible
query `"designer ballgown size XXS under $5"`:

```
$ python -c "from agent import run_agent; from utils.data_loader import get_example_wardrobe; \
  s = run_agent('designer ballgown size XXS under $5', get_example_wardrobe()); \
  print('error:', s['error']); print('fit_card:', s['fit_card'])"

error: No matches for 'designer ballgown' under $5 in size XXS. Try raising your
       budget, dropping the size filter, or broader keywords.
fit_card: None
```

The message tells the user *what failed and what to try* — not just "no results."
A test (`test_agent_skips_llm_tools_on_empty_search`) monkeypatches both LLM tools to
raise if called, and confirms the agent finishes this query without ever touching
them. All failure modes are covered in
[`tests/test_failure_modes.py`](tests/test_failure_modes.py) (29 tests total pass).

---

## AI Usage

I used Claude (in Claude Code) to help implement this project, one component at a
time, and reviewed/revised every output against my `planning.md` spec before
trusting it.

**Instance 1 — implementing `search_listings`.** I gave Claude the Tool 1 spec from
`planning.md` (parameter names and types, the return-field list, and the
"return `[]`, never raise" rule) plus the function docstring's numbered TODO and the
`load_listings()` signature. It produced a pure-Python filter-then-score function. I
**verified and adjusted** before accepting: I confirmed the size filter was a
case-insensitive *substring* match (so `"M"` correctly matches `"S/M"`), and I
checked the price filter was *inclusive* (`price <= max_price`) to match my spec. I
then ran it against three queries — a normal one (expected the Y2K Baby Tee on top),
an impossible one (expected `[]`), and a price-capped one — before moving on.

**Instance 2 — implementing the planning loop in `run_agent`.** I gave Claude the
Planning Loop section, the State Management table, and the ASCII architecture diagram
from `planning.md`. The first generated version called all three tools in sequence,
which **violated my single-branch design** — it would have called `suggest_outfit`
even when `search_listings` returned `[]`. I overrode that: I had it add the
early-`return` on empty results *before* the selection step, and I wrapped the
`suggest_outfit` call in a try/except so an LLM failure sets `error` instead of
crashing the loop. I verified the fix with identity (`is`) checks proving the same
`selected_item` object flows into both `suggest_outfit` and `create_fit_card`, and
with a test that fails if the LLM tools run on an empty search.

---

## Spec Reflection

The biggest payoff was writing the State Management table *before* coding: because
every field had a single writer and known readers, the planning loop was almost
mechanical to implement, and "is state really flowing?" became a checkable claim
(the `is`-identity tests) rather than a hope. The place reality pushed back on the
spec was query parsing — my plan assumed clean inputs like `"vintage tee under $30
size M"`, but conversational queries ("I mostly wear baggy jeans…") leak filler words
into the `description`. Keyword scoring tolerates that (non-matching words just score
0), so I kept the simple regex parser rather than reaching for an LLM, but a stretch
version would parse the query with the LLM for cleaner keywords. The single-branch
design held up well: keeping exactly one decision point (empty vs. non-empty search)
made the agent easy to reason about and made "behaves differently on different
inputs" trivial to demonstrate.

---

## Project Layout

```
ai201-project2-fitfindr-starter/
├── agent.py                 # planning loop (run_agent) + query parser
├── app.py                   # Gradio UI + handle_query()
├── tools.py                 # the three tools
├── planning.md              # design doc (specs, loop, state, architecture)
├── data/
│   ├── listings.json        # 40 mock secondhand listings
│   └── wardrobe_schema.json # wardrobe format + example/empty wardrobes
├── utils/data_loader.py     # data loading helpers
├── tests/
│   ├── test_tools.py        # per-tool tests
│   └── test_failure_modes.py# deliberate failure-mode tests
└── pytest.ini               # registers the `live` marker
```

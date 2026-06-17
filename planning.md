# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (from `load_listings()`) for items matching the user's keywords, filtered by an optional size and price ceiling. It scores each listing by keyword overlap and returns the matches ranked best-first.

**Input parameters:**
- `description` (str): keywords for the desired item, e.g. `"vintage graphic tee"`. Scored against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): size to filter by. Matched case-insensitively as a substring, so `"M"` matches `"S/M"`. `None` skips the size filter.
- `max_price` (float | None): inclusive price ceiling — a listing passes if `price <= max_price`. `None` skips the price filter.

**What it returns:**
A `list[dict]` of matching listings, sorted by relevance score (highest first). Each dict has these fields: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Listings with a keyword score of 0 are dropped before returning.

**What happens if it fails or returns nothing:**
Returns `[]` — it never raises. The planning loop sees the empty list, sets `session["error"]` to a message telling the user which filter to loosen (raise the budget, drop the size, or use broader keywords), and returns early. `suggest_outfit` is not called.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the chosen listing plus the user's wardrobe and asks the LLM (Groq) for 1–2 outfit ideas. If the wardrobe has items, it styles the new piece against pieces the user already owns. If it's empty, it gives general styling advice for the item on its own.

**Input parameters:**
- `new_item` (dict): one listing dict (the `selected_item` from search). Uses its `title`, `category`, `colors`, `style_tags`, and `description` to build the prompt.
- `wardrobe` (dict): a dict with an `items` key holding wardrobe-item dicts (`id`, `name`, `category`, `colors`, `style_tags`, optional `notes`). May be empty: `{"items": []}`.

**What it returns:**
A non-empty string with 1–2 outfit suggestions. With a filled wardrobe it names real pieces (e.g. "pair with your baggy straight-leg jeans and chunky white sneakers") plus a styling tip. With an empty wardrobe it returns general advice about what pairs well and what vibe the item suits.

**What happens if it fails or returns nothing:**
An empty wardrobe is not an error — the tool returns general advice instead of `""`. If the LLM call itself raises, the loop catches it, sets `session["error"]` to "couldn't generate styling," and stops before `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Turns the chosen item and its outfit suggestion into a short, casual caption ready to post (like a real OOTD/thrift-haul post). It calls the LLM at a higher temperature so captions vary between runs.

**Input parameters:**
- `outfit` (str): the styling string from `suggest_outfit()`. Gives the caption its vibe and specific pairings.
- `new_item` (dict): the listing dict for the item. Supplies `title`, `price`, and `platform` to mention once each.

**What it returns:**
A 2–4 sentence caption string for Instagram/TikTok: casual tone, item name + price + platform each mentioned once, outfit vibe in specific terms.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the tool returns a descriptive error string instead of inventing a caption. The loop normally never reaches this, since a failed `suggest_outfit` already ended the run with `session["error"]` set.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a fixed sequence with one early-exit branch, driven by the `session` dict. It does not free-form decide — each step's output determines whether the next step runs.

1. **Initialize.** `session = _new_session(query, wardrobe)`.
2. **Parse the query.** Extract `description`, `size`, and `max_price` from `query` (regex/string parsing: a `$NN`/`under NN` pattern → `max_price`; a `size X` token → `size`; the remaining words → `description`). Store as `session["parsed"]`. If no usable `description` can be extracted, set `session["error"]` and return early.
3. **Search.** Call `search_listings(**session["parsed"])`; store the list in `session["search_results"]`.
   - **Branch — empty:** `if not session["search_results"]:` set `session["error"]` to a message that names which filter to loosen, then **return the session early.** Do not call `suggest_outfit`.
   - **Branch — non-empty:** set `session["selected_item"] = session["search_results"][0]` (top-ranked) and continue.
4. **Suggest outfit.** Call `suggest_outfit(session["selected_item"], session["wardrobe"])`; store the string in `session["outfit_suggestion"]`. (An empty wardrobe is fine — the tool returns general advice, not an error.) If the call raises, catch it, set `session["error"]`, and return early.
5. **Create fit card.** Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`; store the string in `session["fit_card"]`.
6. **Done.** Return `session`. The loop knows it's finished when `fit_card` is set (success) or when any step set `error` (early exit).

**Termination:** there is no repeat/iteration — the loop runs each stage at most once and ends after step 5 (success) or at the first step that sets `error`.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session()`) is the source of truth for one interaction. Each stage reads the fields it needs and writes its output back, so tools never call each other directly — the loop threads state between them.

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` (str) | `_new_session` | parse step |
| `parsed` (dict: description, size, max_price) | parse step | `search_listings` |
| `search_results` (list[dict]) | `search_listings` | empty-check branch, selection |
| `selected_item` (dict) | selection (`search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` (dict) | caller / `_new_session` | `suggest_outfit` |
| `outfit_suggestion` (str) | `suggest_outfit` | `create_fit_card` |
| `fit_card` (str) | `create_fit_card` | final output |
| `error` (str or None) | any step that exits early | caller (checked first) |

The caller checks `session["error"]` first: if not `None`, the run ended early and `outfit_suggestion`/`fit_card` are `None`; otherwise all three output fields are populated. State lives only for the duration of one `run_agent` call — there is no cross-session persistence.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Tool returns `[]`. Loop sets `session["error"]` to a helpful message ("No matches under $30 in size M — try raising your budget, dropping the size filter, or broader keywords") and returns early. `suggest_outfit` is never called with empty input. |
| suggest_outfit | Wardrobe is empty | Not treated as an error. Tool detects `wardrobe["items"] == []` and returns general styling advice for the item alone, so the run still produces a fit card. (If the LLM call itself raises, loop catches it, sets `session["error"]`, and stops.) |
| create_fit_card | Outfit input is missing or incomplete | Tool guards against an empty/whitespace `outfit` and returns a descriptive error string instead of a caption. In practice the loop won't reach here with empty input, since a failed `suggest_outfit` already ended the run with `error` set. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
                ┌──────────────────────────────┐
   User query → │        PLANNING LOOP          │ ←→  SESSION (state dict)
   + wardrobe   │        (run_agent)            │     query, parsed,
                └──────────────────────────────┘     search_results,
                              │                       selected_item, wardrobe,
                              ▼                       outfit_suggestion,
                      parse query                     fit_card, error
                              │  parsed → session
                              ▼
                   ┌───────────────────┐
                   │  search_listings  │  reads parsed
                   └───────────────────┘  writes search_results
                              │
              results == [] ? │
              ┌───────────────┴───────────────┐
              │ yes                            │ no
              ▼                                ▼
     set session["error"]            selected_item = results[0]
     return early  ──► EXIT                    │
     (no later tools)                          ▼
                                    ┌───────────────────┐
                                    │  suggest_outfit   │  reads selected_item, wardrobe
                                    └───────────────────┘  writes outfit_suggestion
                                    (empty wardrobe → general advice, not error)
                                               │
                                               ▼
                                    ┌───────────────────┐
                                    │  create_fit_card  │  reads outfit_suggestion, selected_item
                                    └───────────────────┘  writes fit_card
                                               │
                                               ▼
                                     return session ──► output
                                  (listing + outfit + fit card)
```

Every tool reads from and writes to the shared SESSION dict — tools never call each
other directly. The only branch is the empty-results check after `search_listings`,
which is the single early-exit path.

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

I'll use Claude (in Claude Code) one tool at a time, never all three at once.
- **search_listings:** give Claude the Tool 1 spec (inputs, return fields, the `[]`-on-no-match rule) plus the docstring TODO and `load_listings()`. Expect a pure-Python filter+keyword-score function (no LLM). Verify before trusting: run 3 queries — a normal one ("vintage graphic tee", size M, $30 → expect non-empty, all `price <= 30` and size containing "M"), a too-strict one ("designer ballgown size XXS under $5" → expect `[]`), and a no-filter one — and eyeball that the top result is actually relevant.
- **suggest_outfit:** give Claude the Tool 2 spec, the wardrobe schema, and the empty-wardrobe branch. Expect a function that formats wardrobe items into a Groq prompt and returns a string. Verify: call once with `get_example_wardrobe()` (should name real pieces) and once with `get_empty_wardrobe()` (should still return non-empty general advice, not crash).
- **create_fit_card:** give Claude the Tool 3 spec and style guidelines (casual, mention name/price/platform once, higher temperature). Verify: run it twice on the same outfit and confirm the captions differ and each names the item/price/platform.

**Milestone 4 — Planning loop and state management:**

I'll give Claude the Planning Loop section, the State Management table, the Architecture diagram, and the existing `_new_session`/`run_agent` scaffolding in `agent.py`. Expect it to fill in `run_agent` following the numbered steps — parse → search → empty-check early exit → select top → suggest → fit card → return session. Verify against the two CLI cases already in `agent.py`: the happy-path query (expect `error is None` and a populated `fit_card`) and the no-results query (expect `error` set and `outfit_suggestion`/`fit_card` left `None`). I'll confirm the implementation matches this spec — especially that the empty-results branch returns early and never calls `suggest_outfit` — rather than accepting whatever it generates.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr needs to do (in my own words):** FitFindr takes a shopper's request, finds a secondhand listing that matches it, then helps them wear it. The request triggers `search_listings`; a match triggers `suggest_outfit` (styling the item against the user's wardrobe); a successful outfit triggers `create_fit_card` (the post-ready caption). If `search_listings` finds nothing, the agent stops and tells the user what to change — it never calls the later tools with empty input.

**Example user query:** "I'm looking for a vintage graphic tee under $30 size m. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Search:** The agent parses the query into `description="vintage graphic tee"`, `size="M"`, `max_price=30.0` and calls `search_listings("vintage graphic tee", size="M", max_price=30.0)`. It returns listings ranked by keyword score; the agent picks the top result, `selected_item`. Against the real dataset the top match is `"Y2K Baby Tee — Butterfly Print, $18, depop, excellent condition"`. (If the list were empty, the agent would stop here and tell the user to loosen a filter.)

**Step 2 — Suggest outfit:** The agent calls `suggest_outfit(new_item=<Y2K baby tee>, wardrobe=<user's wardrobe>)`. It returns a suggestion naming real wardrobe pieces: "Pair it with your baggy straight-leg jeans and chunky white sneakers for a Y2K street look. Add the black crossbody to finish."

**Step 3 — Fit card:** The agent calls `create_fit_card(outfit=<suggestion>, new_item=<Y2K baby tee>)`, producing a short caption: "found this y2k butterfly baby tee on depop for $18 and it's perfect with my baggy jeans 🦋 full fit in my stories"

**Final output to user:** The user sees all three in one response — the matched listing (title, price, platform, condition), the styling suggestion built from their own wardrobe, and the ready-to-post fit card caption.

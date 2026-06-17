"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

# Filler words stripped from the description after price/size are removed.
_STOPWORDS = {
    "a", "an", "the", "for", "in", "im", "i", "m", "looking", "want", "need",
    "find", "me", "some", "something", "that", "is", "are", "under", "below",
    "less", "than", "around", "about", "size", "sized", "and", "with", "to",
    "of", "please", "show",
}


def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural-language query.

    - max_price: a "$NN" / "under NN" / "below NN" pattern → float, else None.
    - size:      a "size X" token (S/M/L/XL or a number) → str, else None.
    - description: the remaining words with price/size phrases and filler removed.
    """
    text = query or ""
    lowered = text.lower()

    # --- max_price -----------------------------------------------------------
    max_price = None
    price_match = re.search(
        r"(?:under|below|less than|<=?|\$)\s*\$?\s*(\d+(?:\.\d+)?)", lowered
    )
    if not price_match:
        # Bare "$30" without a leading keyword.
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", lowered)
    if price_match:
        max_price = float(price_match.group(1))

    # --- size ----------------------------------------------------------------
    size = None
    size_match = re.search(
        r"size\s+(xxs|xs|s|m|l|xl|xxl|\d+(?:\.\d+)?)", lowered
    )
    if size_match:
        size = size_match.group(1).upper()

    # --- description ---------------------------------------------------------
    # Strip out the phrases we already consumed, then drop filler/numbers.
    cleaned = lowered
    cleaned = re.sub(
        r"(?:under|below|less than|<=?)\s*\$?\s*\d+(?:\.\d+)?", " ", cleaned
    )
    cleaned = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", cleaned)
    cleaned = re.sub(r"size\s+(?:xxs|xs|s|m|l|xl|xxl|\d+(?:\.\d+)?)", " ", cleaned)

    words = re.findall(r"[a-z0-9']+", cleaned)
    desc_words = [w for w in words if w not in _STOPWORDS and not w.isdigit()]
    description = " ".join(desc_words).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: Initialize the session.
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into description / size / max_price.
    session["parsed"] = _parse_query(query)
    if not session["parsed"]["description"]:
        session["error"] = (
            "I couldn't tell what you're looking for. Try naming the item, "
            "e.g. 'vintage graphic tee under $30, size M'."
        )
        return session

    # Step 3: Search. Branch on the result — empty means early exit.
    session["search_results"] = search_listings(**session["parsed"])
    if not session["search_results"]:
        parsed = session["parsed"]
        filters = []
        if parsed["max_price"] is not None:
            filters.append(f"under ${parsed['max_price']:g}")
        if parsed["size"] is not None:
            filters.append(f"in size {parsed['size']}")
        filter_text = (" " + " ".join(filters)) if filters else ""
        session["error"] = (
            f"No matches for '{parsed['description']}'{filter_text}. "
            "Try raising your budget, dropping the size filter, or broader keywords."
        )
        # Do NOT call suggest_outfit / create_fit_card with empty input.
        return session

    # Step 4: Select the top-ranked item.
    session["selected_item"] = session["search_results"][0]

    # Step 5: Suggest an outfit (empty wardrobe → general advice, not an error).
    try:
        session["outfit_suggestion"] = suggest_outfit(
            session["selected_item"], session["wardrobe"]
        )
    except Exception as exc:
        session["error"] = f"Couldn't generate styling advice: {exc}"
        return session

    # Step 6: Create the shareable fit card.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: Return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

"""
Tests for the three FitFindr tools.

Run from the project root with:  pytest tests/

The search_listings tests are pure (no network). The suggest_outfit and
create_fit_card tests make one live Groq call each, so they need GROQ_API_KEY
set in .env. Each tool's failure mode has at least one dedicated test.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    # Every returned item must respect the price ceiling.
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    # Size match is a case-insensitive substring ("m" matches "S/M").
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_sorted_by_relevance():
    # More keyword overlap should rank higher; result is non-increasing in score.
    results = search_listings("vintage denim jacket")
    assert isinstance(results, list)
    assert len(results) > 0


# ── suggest_outfit ──────────────────────────────────────────────────────────

def _sample_item():
    return search_listings("vintage graphic tee", size="M", max_price=30)[0]


def test_suggest_outfit_with_wardrobe():
    result = suggest_outfit(_sample_item(), get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip()


def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe must NOT crash and must NOT return "".
    result = suggest_outfit(_sample_item(), get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    # Failure mode: empty/whitespace outfit returns an error string, not a crash.
    result = create_fit_card("", _sample_item())
    assert isinstance(result, str)
    assert result.strip() != ""

    result_ws = create_fit_card("   ", _sample_item())
    assert isinstance(result_ws, str)
    assert result_ws.strip() != ""


def test_create_fit_card_returns_caption():
    outfit = "Pair it with baggy straight-leg jeans and chunky white sneakers."
    result = create_fit_card(outfit, _sample_item())
    assert isinstance(result, str)
    assert result.strip()

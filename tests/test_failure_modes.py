"""
Milestone 5 — deliberate failure-mode tests.

Each tool's failure mode (and several extra edge cases) is triggered on purpose
and asserted to recover gracefully: a specific, informative string or an empty
list — never an unhandled exception.

Cases marked LIVE make a real Groq call (need GROQ_API_KEY). The rest are pure
or use a fake Groq client (FakeClient) so they run fast and free, and so we can
deterministically simulate an LLM that raises mid-run.

Run from the project root with:  pytest tests/
"""

import pytest

import tools
import agent
from tools import search_listings, suggest_outfit, create_fit_card
from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── test doubles ──────────────────────────────────────────────────────────────

class _FakeMessage:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _FakeCompletions:
    def __init__(self, content, raises):
        self._content = content
        self._raises = raises

    def create(self, **kwargs):
        if self._raises:
            raise RuntimeError("simulated Groq API failure")
        return type("R", (), {"choices": [_FakeMessage(self._content)]})


class FakeClient:
    """Stand-in for the Groq client. Returns canned text or raises on demand."""

    def __init__(self, content="canned styling advice for the item", raises=False):
        self.chat = type(
            "C", (), {"completions": _FakeCompletions(content, raises)}
        )


@pytest.fixture
def fake_groq(monkeypatch):
    """Patch tools._get_groq_client to return a FakeClient (no network)."""
    def _install(content="canned styling advice for the item", raises=False):
        monkeypatch.setattr(
            tools, "_get_groq_client", lambda: FakeClient(content, raises)
        )
    return _install


SAMPLE_ITEM = {
    "id": "lst_x",
    "title": "Y2K Baby Tee",
    "description": "cute butterfly print",
    "category": "tops",
    "style_tags": ["y2k", "vintage"],
    "size": "S/M",
    "condition": "excellent",
    "price": 18.0,
    "colors": ["pink"],
    "brand": None,
    "platform": "depop",
}


# ── Failure mode 1: search_listings returns zero results ────────────────────────

def test_search_zero_results_no_exception():
    # The milestone trigger — impossible query must return [] and not raise.
    assert search_listings("designer ballgown", size="XXS", max_price=5) == []


def test_search_empty_description():
    # No keywords at all → nothing can score > 0 → [].
    assert search_listings("") == []


def test_search_whitespace_description():
    assert search_listings("   ") == []


def test_search_punctuation_only_description():
    assert search_listings("!!! ??? ...") == []


def test_search_zero_max_price():
    # Nothing is free → [], no crash.
    assert search_listings("tee", size=None, max_price=0) == []


def test_search_nonmatching_size():
    # A size string that appears in no listing → [].
    assert search_listings("tee", size="XXXL") == []


def test_search_nonsense_keywords():
    assert search_listings("zxqw flumph gribble") == []


def test_agent_impossible_query_is_informative():
    # Full agent on the impossible query: error names what to loosen, no fit card.
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert session["error"] is not None
    assert session["fit_card"] is None
    assert session["outfit_suggestion"] is None
    assert session["selected_item"] is None
    # Not just "no results" — it must tell the user what to try.
    assert "try" in session["error"].lower()


def test_agent_empty_query_is_informative():
    session = run_agent("", get_example_wardrobe())
    assert session["error"] is not None
    assert session["fit_card"] is None


def test_agent_query_with_no_item_words():
    # Only filters, no describable item → can't search → informative error.
    session = run_agent("under $30 size M", get_example_wardrobe())
    assert session["error"] is not None
    assert session["fit_card"] is None


def test_agent_skips_llm_tools_on_empty_search(monkeypatch):
    # The branch test: when search is empty, the LLM tools must NEVER be called.
    def _boom(*args, **kwargs):
        raise AssertionError("LLM tool called despite empty search results!")

    monkeypatch.setattr(agent, "suggest_outfit", _boom)
    monkeypatch.setattr(agent, "create_fit_card", _boom)

    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert session["error"] is not None  # reached here without _boom firing


# ── Failure mode 2: suggest_outfit with an empty wardrobe ───────────────────────

def test_suggest_outfit_empty_wardrobe_fake(fake_groq):
    # Deterministic: empty wardrobe still produces a non-empty string, no crash.
    fake_groq(content="general styling advice")
    out = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
    assert isinstance(out, str) and out.strip()


def test_suggest_outfit_missing_items_key(fake_groq):
    # Defensive: a wardrobe dict with no 'items' key must not raise.
    fake_groq()
    out = suggest_outfit(SAMPLE_ITEM, {})
    assert isinstance(out, str) and out.strip()


def test_suggest_outfit_sparse_item(fake_groq):
    # new_item missing most fields → prompt building must not KeyError.
    fake_groq()
    out = suggest_outfit({"title": "Mystery item"}, get_empty_wardrobe())
    assert isinstance(out, str) and out.strip()


@pytest.mark.live
def test_suggest_outfit_empty_wardrobe_live():
    # The milestone trigger with a real Groq call.
    out = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
    assert isinstance(out, str)
    assert out.strip() != ""


def test_agent_recovers_when_suggest_outfit_raises(monkeypatch):
    # If the LLM call inside suggest_outfit raises, the loop catches it,
    # sets error, and never reaches create_fit_card.
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(agent, "suggest_outfit", _raise)
    monkeypatch.setattr(
        agent, "create_fit_card",
        lambda *a, **k: pytest.fail("create_fit_card ran after suggest failed"),
    )

    session = run_agent("vintage graphic tee under $30", get_example_wardrobe())
    assert session["error"] is not None
    assert session["fit_card"] is None


# ── Failure mode 3: create_fit_card with an empty / bad outfit ──────────────────

def test_create_fit_card_empty_string():
    # The milestone trigger — empty outfit returns an error string, not a crash.
    result = create_fit_card("", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_whitespace_outfit():
    result = create_fit_card("   \n  ", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_none_outfit():
    # Defensive: a None outfit must hit the guard, not raise.
    result = create_fit_card(None, SAMPLE_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_guard_skips_llm(monkeypatch):
    # The empty-outfit guard must return BEFORE any Groq call is made.
    monkeypatch.setattr(
        tools, "_get_groq_client",
        lambda: pytest.fail("Groq client created despite empty outfit"),
    )
    result = create_fit_card("", SAMPLE_ITEM)
    assert isinstance(result, str) and result.strip()

# tests/test_tools.py
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe
from agent import _parse_query, run_agent
import agent


# ── search_listings tests ─────────────────────────────────────────────────────

def test_search_returns_results():
    # basic happy path — should return at least one result
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # failure mode — no listings match, should return empty list not crash
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    # inclusive cap — no results should exceed max_price
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_retry_relaxes_filters():
    # size XXS matches nothing — confirms retry with relaxed filters finds results
    results = search_listings("vintage tee", size="XXS", max_price=None)
    assert results == []
    results = search_listings("vintage tee", size=None, max_price=None)
    assert len(results) > 0


# ── suggest_outfit tests ──────────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe():
    # failure mode — empty wardrobe should not crash, must return a non-empty string
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 0


# ── create_fit_card tests ─────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    # failure mode — empty outfit string should return error message string, not crash
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    card = create_fit_card("", results[0])
    assert isinstance(card, str)
    assert len(card) > 0


# ── _parse_query tests ────────────────────────────────────────────────────────

def test_parse_query_exclusive_price():
    # "under $30" is exclusive — should subtract 0.01 giving 29.99
    result = _parse_query("vintage graphic tee under $30")
    assert result["max_price"] == 29.99


def test_parse_query_inclusive_price():
    # "$50 or under" is inclusive — should keep number as-is
    result = _parse_query("jacket $50 or under size M")
    assert result["max_price"] == 50.0


def test_parse_query_no_filters():
    # no price or size mentioned — both should be None
    result = _parse_query("blue jeans")
    assert result["max_price"] is None
    assert result["size"] is None


# ── session calls tracking tests ──────────────────────────────────────────────

def test_session_calls_tracking():
    # after a successful run, each tool should have been called at least once
    session = run_agent("vintage graphic tee under $30", get_example_wardrobe())
    assert session["calls"]["search_listings"] >= 1
    assert session["calls"]["suggest_outfit"] >= 1
    assert session["calls"]["create_fit_card"] >= 1


# ── MAX_SEARCH_FALLBACKS tests ────────────────────────────────────────────────

def test_search_fallback_respects_max():
    # with MAX_SEARCH_FALLBACKS = 1, only one attempt should be made — no relaxation
    original = agent.MAX_SEARCH_FALLBACKS
    agent.MAX_SEARCH_FALLBACKS = 1
    try:
        session = {"calls": {"search_listings": 0}, "search_note": None}
        agent._search_with_fallback("vintage tee", "XXS", 1.0, session)
        assert session["calls"]["search_listings"] == 1
        assert session["search_note"] is None
    finally:
        agent.MAX_SEARCH_FALLBACKS = original


def test_search_fallback_sets_note():
    # with MAX_SEARCH_FALLBACKS = 4, relaxation should happen and note should be set
    # when filters are too strict to find results on first attempt
    session = {"calls": {"search_listings": 0}, "search_note": None}
    results = agent._search_with_fallback("vintage tee", "XXS", 1.0, session)
    # more than one attempt should have been made since filters were too strict
    assert session["calls"]["search_listings"] > 1
    # if results were found via fallback, note should be set
    if results:
        assert session["search_note"] is not None
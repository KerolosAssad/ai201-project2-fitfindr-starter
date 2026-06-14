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

from tools import search_listings, suggest_outfit, create_fit_card
from utils.groq_client import get_groq_client
import json



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
        "calls": {                   # tracks how many times each tool was called
            "search_listings": 0,
            "suggest_outfit": 0,
            "create_fit_card": 0,
        },
    }


# ── planning loop ─────────────────────────────────────────────────────────────

# max number of tool calls allowed before forcing an exit
MAX_ITERATIONS = 3 # max attempts per individual tool

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using an LLM. Chosen over regex because it handles natural language
    variations without requiring us to anticipate every possible phrasing.
    Only one API call is made at the start of the interaction before any
    tools run, so the added latency is minimal.

    Returns a dict with keys: description (str), size (str or None),
    max_price (float or None). For exclusive phrasings like "under $30",
    the LLM subtracts 0.01 so $30.00 listings are excluded naturally with
    search_listings' inclusive cap (price <= max_price). For inclusive
    phrasings like "up to $30" or "$30 or under", the number is kept as-is.
    """
    client = get_groq_client()

    prompt = (
        f"Extract search parameters from this query and return ONLY a JSON object "
        f"with exactly these three fields:\n"
        f"  - description (str): the item being searched for\n"
        f"  - size (str or null): the size if mentioned, null if not\n"
        f"  - max_price (float or null): the maximum price if mentioned, null if not\n\n"
        f"Rules:\n"
        f"  - For description, extract only the item name — not the full query\n"
        f"  - For max_price, if the phrasing is exclusive ('under', 'less than', 'below'), "
        f"subtract 0.01 from the number (e.g. 'under $30' → 29.99, 'less than $30' → 29.99)\n"
        f"  - For max_price, if the phrasing is inclusive ('up to', 'or under', 'or less', "
        f"'and under', 'max', 'no more than', 'at most', '$X or under', '$X or less'), "
        f"keep the number as-is (e.g. '$50 or under' → 50.0, 'up to $30' → 30.0)\n"
        f"  - Return only the JSON object, no explanation, no markdown, no backticks\n\n"
        f"Query: {query}"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100,
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # if the LLM returns malformed JSON, fall back to using the full
        # query as description with no size or price filter
        return {"description": query, "size": None, "max_price": None}

    return {
        "description": parsed.get("description", query),
        "size": parsed.get("size", None),
        "max_price": float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
    }

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
    # TODO: implement the planning loop
    # step 1: initialize session with per-tool call tracking
    session = _new_session(query, wardrobe)

    # step 2: parse query into description, size, max_price using LLM
    # no retry here — if parsing fails it falls back to using the full query
    session["parsed"] = _parse_query(query)
    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]

    # step 3: call search_listings — deterministic, so only retry once
    # with relaxed filters if the first attempt returns empty
    session["search_results"] = search_listings(description, size, max_price)
    session["calls"]["search_listings"] += 1

    if not session["search_results"]:
        # retry once with relaxed filters — drop size and price since
        # search_listings is deterministic and retrying with same inputs
        # would always return the same empty result
        session["search_results"] = search_listings(description, None, None)
        session["calls"]["search_listings"] += 1

        if not session["search_results"]:
            session["error"] = (
                "No listings matched your query. Try broadening your description, "
                "adjusting your size, or raising your max price."
            )
            return session

    # step 4: select top result
    session["selected_item"] = session["search_results"][0]

    # step 5: call suggest_outfit — LLM based, retry up to MAX_ITERATIONS
    # times since LLM calls can fail transiently (network timeout, rate limit)
    # or return 'NONE' if the LLM signals it cannot generate a valid suggestion
    outfit_attempts = 0
    while outfit_attempts < MAX_ITERATIONS:
        session["outfit_suggestion"] = suggest_outfit(session["selected_item"], wardrobe)
        session["calls"]["suggest_outfit"] += 1
        outfit_attempts += 1
        if session["outfit_suggestion"] and session["outfit_suggestion"].strip() != "NONE":
            break

    if not session["outfit_suggestion"] or session["outfit_suggestion"].strip() == "NONE":
        session["error"] = (
            "Could not generate an outfit suggestion after multiple attempts. "
            "Please try a different query."
        )
        return session

    # step 6: call create_fit_card — LLM based, retry up to MAX_ITERATIONS
    # times since LLM calls can fail transiently or return 'NONE'
    fitcard_attempts = 0
    while fitcard_attempts < MAX_ITERATIONS:
        session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])
        session["calls"]["create_fit_card"] += 1
        fitcard_attempts += 1
        if session["fit_card"] and session["fit_card"].strip() != "NONE":
            break

    if not session["fit_card"] or session["fit_card"].strip() == "NONE":
        session["error"] = (
            "Could not generate a fit card after multiple attempts. "
            "Outfit suggestion is still available above."
        )
        return session

    # step 7: return completed session
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

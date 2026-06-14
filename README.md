# FitFindr — Starter Kit

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   ├── data_loader.py         # Helper functions for loading the data
│   └── groq_client.py         # Shared Groq client initialization
├── tools.py                   # Three agent tools: search_listings, suggest_outfit, create_fit_card
├── agent.py                   # Planning loop that orchestrates the tools
├── app.py                     # Gradio UI
├── tests/
│   └── test_tools.py          # pytest tests for each tool failure mode
├── planning.md                # Planning document — filled out before implementation
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

---

## Tool Inventory

### `search_listings(description: str, size: str | None, max_price: float | None) → list[dict]`
Searches `listings.json` for items matching the user's query. Relevance is scored by keyword overlap between `description` and each listing's `title`, `description`, `category`, and `style_tags` fields using whole-word matching to avoid false positives. Optional `size` and `max_price` filters are applied first. Returns a list of up to 3 matching listing dicts sorted by relevance score; returns an empty list if nothing matches, does not raise an exception.

### `suggest_outfit(new_item: dict, wardrobe: dict) → str`
Takes the top listing from `search_listings` and the user's wardrobe and uses an LLM (`llama-3.3-70b-versatile` via Groq) to generate 1–2 outfit suggestions pairing the new item with existing wardrobe pieces. If the wardrobe is empty, returns general styling advice for the item instead of specific combinations. Returns `'NONE'` if the LLM signals it cannot generate a valid suggestion.

### `create_fit_card(outfit: str, new_item: dict) → str`
Takes the styling suggestion from `suggest_outfit` and the top listing dict and uses an LLM to generate a short, casual 2–4 sentence social media caption mentioning the item name, price, and platform naturally. Temperature is set to 1.2 to ensure varied output across runs. Returns a descriptive error message string if `outfit` is empty rather than raising an exception. Returns `'NONE'` if the LLM signals it cannot generate a valid caption.

---

## Planning Loop

The agent runs a sequence of tool calls with conditional branching and retry logic at each step:

1. Parse the user's query using an LLM (`_parse_query`) to extract `description`, `size`, and `max_price`. Exclusive phrasings like "under $30" are converted to 29.99; inclusive phrasings like "$50 or under" keep the number as-is. If the LLM returns malformed JSON, falls back to using the full query as description with no filters.
2. Call `search_listings`. If results are empty, retry once with relaxed filters (dropping `size` and `max_price`). If still empty, set `session["error"]` and return early; `suggest_outfit` is never called with empty input.
3. Set `selected_item = results[0]` and call `suggest_outfit`. Since this is LLM-based, retry up to `MAX_ITERATIONS` (3) times if it returns nothing or `'NONE'`. If all attempts fail, set `session["error"]` and return early; `create_fit_card` is never called.
4. Call `create_fit_card` with the outfit suggestion and selected item. Also LLM-based — retry up to `MAX_ITERATIONS` (3) times on failure or `'NONE'`. If all attempts fail, surface the outfit suggestion directly and note the fit card could not be generated.
5. Return the completed session dict.

Each tool call is tracked in `session["calls"]` for debugging and transparency.

---

## State Management

The agent tracks five pieces of state in a session dict across tool calls:

- `selected_item` (dict): the top listing from `search_listings`, passed as `new_item` to both `suggest_outfit` and `create_fit_card`
- `outfit_suggestion` (str): the string returned by `suggest_outfit`, passed as `outfit` to `create_fit_card`
- `wardrobe` (dict): passed in as a parameter to `run_agent()` and stored in the session from the start via `_new_session()` — supports both `get_example_wardrobe()` and `get_empty_wardrobe()` as selected by the user in the UI
- `fit_card` (str): the final caption returned by `create_fit_card`
- `calls` (dict): tracks how many times each tool was called independently, including retries, for debugging and transparency

All values are held in the session dict and passed directly between tool calls. No external store is used.

---

## Error Handling

| Tool | Failure mode | Agent response | Example from testing |
|------|-------------|----------------|----------------------|
| `search_listings` | No results match the query | Retries once with relaxed filters (dropping `size` and `max_price`). If still empty, sets `session["error"]` and returns early — `suggest_outfit` is never called. | Running `search_listings("designer ballgown", size="XXS", max_price=5)` returns `[]`. Full agent run sets `session["error"] = "No listings matched your query. Try broadening your description, adjusting your size, or raising your max price."` and `session["fit_card"] = None`. |
| `suggest_outfit` | Wardrobe is empty | Falls back to general styling advice for the item rather than specific outfit combinations. Agent continues to `create_fit_card`. | Running `suggest_outfit(results[0], get_empty_wardrobe())` returned general styling advice for the Y2K Baby Tee — two outfit ideas with no wardrobe-specific pieces referenced. |
| `create_fit_card` | Outfit input is empty or missing | Returns a descriptive error message string instead of raising an exception. Agent surfaces the outfit suggestion from `suggest_outfit` directly to the user. | Running `create_fit_card("", results[0])` returned `"Could not generate a fit card — the outfit suggestion was empty. Try resubmitting your query with more details."` |

---

## Spec Reflection

The implementation matches the planning.md spec with several notable decisions made during development:

**Inclusive vs exclusive price cap** — planning.md originally described `max_price` as an exclusive cap. After confirming against the provided test (`assert all(item["price"] <= 10 for item in results)`), the tool was updated to use an inclusive cap (`price <= max_price`). To handle queries like "under $30", the agent converts the user's stated limit to 29.99 at query parsing time so $30.00 listings fall outside the cap naturally.

**Wardrobe loading location** — planning.md originally stated the wardrobe would be loaded inside `suggest_outfit` via `get_example_wardrobe()`. During implementation, this was updated so the wardrobe is passed in as a parameter to `run_agent()` and stored in the session from the start — this was necessary to support the UI's radio button allowing users to choose between the example wardrobe and an empty wardrobe.

**LLM parsing over regex** — query parsing was initially implemented with regex but switched to LLM parsing after identifying that regex required anticipating every possible price phrasing. The LLM parser was also refined after testing revealed that "$50 or under" was incorrectly treated as exclusive — the prompt rules were updated to explicitly distinguish inclusive and exclusive phrasings.

**`NONE` grounding instruction** — a `'NONE'` signal was added to the `suggest_outfit` and `create_fit_card` prompts so the LLM can explicitly signal failure rather than returning unhelpful text that would pass empty/whitespace checks but be useless as output. The agent's retry loops check for `'NONE'` alongside empty strings.

**Defensive coding for external API calls** — following feedback from the previous project about wrapping external calls in error handling, try/except blocks were added around all Groq API calls in suggest_outfit and create_fit_card. A network timeout or rate limit now returns "NONE" rather than crashing the agent, which feeds cleanly into the existing retry loops.

**Shared Groq client** — the Groq client was moved to `utils/groq_client.py` to avoid duplicating initialization logic across `tools.py` and `agent.py`. This directly addresses the separation of concerns feedback from the previous project.

---

## AI Usage

**Instance 1 — Implementing `search_listings`:**
I gave Claude the Tool 1 spec block from planning.md — including the input parameters, return value, and failure mode — and asked it to implement the function using `load_listings()` from `data_loader.py`. It produced a working implementation with keyword scoring and price/size filtering. Before using it, I reviewed the scoring logic and identified that `kw in searchable` was a substring check — "tee" would match inside "streetwear." I overrode this by switching to `re.search(r"\b" + re.escape(kw) + r"\b", searchable)` for whole-word matching and added a comment explaining the change.

**Instance 2 — Implementing `run_agent`:**
I gave Claude the Planning Loop and State Management sections of planning.md along with the architecture diagram and asked it to implement the planning loop in `agent.py`. It produced a working loop that branched correctly on `search_results` and stored values in the session dict. Before using it, I reviewed the wardrobe handling and identified a mismatch with planning.md — the generated code passed the wardrobe in as a parameter rather than loading it inside `suggest_outfit`. This was actually better than the spec described since it supports both wardrobe choices from the UI, so I kept the change and updated planning.md to reflect it.

**Instance 3 — Resolving the `max_price` inclusive vs exclusive cap and switching to LLM parsing:**
During a planning discussion, the initial spec described `max_price` as an exclusive cap. Claude flagged a conflict with the provided test (`assert all(item["price"] <= 10 for item in results)`), which expects inclusive behavior. The resolution was to use an inclusive cap in the tool and handle "under $30" at query parsing time by converting it to 29.99. Query parsing was initially implemented with regex, but after identifying that regex required anticipating every possible phrasing, it was switched to LLM parsing. Testing then revealed that "$50 or under" was incorrectly treated as exclusive — the prompt rules were updated to explicitly list inclusive phrasings. Both planning.md and the implementation were updated to reflect these decisions.

**Instance 4 — Adding `NONE` grounding and per-tool retry loops:**
During implementation, it was identified that the retry conditions for `suggest_outfit` and `create_fit_card` only checked for empty or whitespace output — the LLM could return unhelpful text like "I don't know" that would pass the check but be useless. Rather than checking for refusal phrases after the fact, a `'NONE'` grounding instruction was added to both prompts so the LLM signals failure explicitly. The agent's retry loops were updated to check for `'NONE'` alongside empty strings. `search_listings` was given a single retry with relaxed filters rather than a loop since it's deterministic — retrying with the same inputs would always return the same result. `session["calls"]` was also added to track per-tool call counts for debugging.
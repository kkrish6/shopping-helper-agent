# Shopping Helper Agent

An AI-assisted shopping tool for Indian e-commerce. Give it a product and it searches Flipkart and Amazon.in, finds cheaper similar alternatives, and tracks prices so you can tell a real deal from an inflated MRP.

**Live demo:** https://kkrish-price-agent.streamlit.app/ (free hosting, sleeps when idle, so the first load can take ~30 s)

## What it does

1. **Search** Flipkart and Amazon.in for a product.
2. **Find cheaper, similar alternatives** and rank them by value.
3. **Track prices** in SQLite and flag price drops, target-price hits and fake "big discounts".
4. **LangChain Agent tab and CLI** use an optional tool-capable OpenAI-compatible model to choose search, comparison and price-history tools. Prices and savings are rendered from Python tool facts, never model-written advice. Without a key, explicit rule-based mode keeps working.

## Quick start

```bash
git clone https://github.com/kkrish6/shopping-helper-agent && cd shopping-helper-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python main.py --sources demo agent "Compare earbuds under 2000" --no-llm
python main.py --sources demo search "earbuds under 2000"   # offline demo
python main.py search "boat airdopes under 1500"            # live
python main.py watch "boat airdopes 141" --target 899
python main.py check
python main.py list
streamlit run streamlit_app.py                                        # web UI
```

Run `check` once or twice a day (cron / Task Scheduler) to build price history.

## Architecture

```
main.py (CLI)  /  streamlit_app.py (Search, Watchlist, Agent tabs)
  ├── agent.py      LangChain tools + agent loop + rules fallback + fact renderer
  ├── llm.py        optional legacy request parsing
  ├── providers.py  Flipkart / Amazon / Demo -> list[Product]; cache + rate limit
  ├── ranking.py    similarity, cheaper-alternative scoring, deal verdict
  └── store.py      SQLite: watchlist + price_history
```

## Design decisions

- **Deterministic tools, LLM for language only.** Fetching, ranking and storage are plain Python. A prompt alone cannot stop made-up prices. The agent discards model answer prose and renders recorded tool facts. If the model fails, explicit rule-based mode still works.
- **Provider interface.** A new store is one class with `search(query) -> list[Product]`.
- **Explainable ranking.** `score = similarity * (0.5 + saving) * rating_factor`, with similarity from token overlap (Jaccard) plus fuzzy matching (`difflib`). Items rated below 3.5 are dropped.
- **Price history, not MRP.** The verdict compares a price with its own history (lowest seen, change since last check) and warns on very large MRP discounts.
- **Polite scraping.** 3 s gap per site, 30 min cache, one retry with backoff, stops on 403/429/503, skips Amazon CAPTCHA pages.
- **SQL design.** `watchlist` (unique URL) and `price_history` (foreign key, indexed on `watch_id, checked_at`).

## Limitations

- Scraping is best effort. Amazon.in often blocks plain requests, so you may only get Flipkart results. For personal, low-volume use; retailer terms restrict automated access.
- "Similar" is text similarity, not model-number or spec matching.
- Bank offers and coupons are not parsed, only listed price vs MRP.
- On the free host the watchlist can reset on restart and prices are checked only on demand.

## Ideas to extend

- Email / Telegram alerts when a target is hit
- More stores (Croma, Myntra) or a price API
- Persistent, per-user storage and wider real-provider testing


## LangChain agent: examples and limits

```bash
python main.py --sources demo agent "Compare earbuds under 2000" --no-llm
python main.py --sources demo agent "Find earbuds under 1000"
python main.py agent "Show price history for watch 1"
```

- `search_products`: provider listings + deterministic budget filtering.
- `compare_products`: existing best-match and alternative ranking + savings arithmetic.
- `price_history`: a read-only snapshot of saved SQLite observations and timestamps, not fresh retailer prices.
- Tools are scoped to the user's selected sources. A regex-recognised explicit budget is enforced in Python even if the model requests a higher one.
- Maximum six tool calls and bounded graph recursion; repeated searches within one request reuse results. Provider HTTP and model timeouts remain in effect.
- Untrusted listing text is data. The system prompt tells the model not to follow it, but that is not a complete prompt-injection defense. Tools are restricted to read-only shopping operations; no purchase, arbitrary URL fetch, file access or watchlist-write tool is exposed.
- Product matching is heuristic, prices can be stale, and no bank/coupon offers are verified. Free-host SQLite can reset and is not a per-user private store.
- Tests exercise actual LangChain orchestration with a scripted chat model, offline sample data, fallback and Streamlit interaction. They do not establish real-provider reasoning quality, successful authenticated inference, or current retailer availability. No live model API test has been run.

Read [LANGCHAIN_LEARNING.md](LANGCHAIN_LEARNING.md) for the walkthrough. Versioned dependencies were tested on Python 3.10.12.


## Configuration and test status

Python 3.10+ is required. Set `LLM_API_KEY`, optionally `LLM_BASE_URL` and `LLM_MODEL`, in the server environment. The model must support tool calling. Defaults inherit the project's existing Groq endpoint and model identifier, which have not been live-verified in this update. Never commit keys. `.env.example` is a reference, not an automatic .env loader.

The repository contains four existing tests in `test_ranking.py` and 20 new agent/UI checks in `test_agent.py`. All 24 passed locally on Python 3.10.12. The LangChain loop was tested using a scripted model, not a live paid/provider inference call. The Agent tool facts view makes the chosen tools inspectable. Existing search no longer displays optional model-written price advice.

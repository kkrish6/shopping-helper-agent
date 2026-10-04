# Shopping Helper Agent

A command line agent for Indian online shopping. Give it a product and it:

1. **Searches** Flipkart and Amazon.in
2. **Finds cheaper, similar alternatives** and ranks them by value
3. **Tracks prices** in SQLite and tells you about price drops, target-price hits and whether a "big discount" is real

It runs fully **without any paid API**. An LLM (free tier) is optional and only adds natural-language input and a short buying summary.

## Quick start

```bash
git clone https://github.com/kkrish6/shopping-helper-agent && cd shopping-helper-agent
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py --sources demo search "earbuds under 2000"   # offline demo, no network
python main.py search "boat airdopes under 1500"            # live (Flipkart + Amazon)
python main.py watch "boat airdopes 141" --target 899       # start tracking a price
python main.py check                                        # re-check all tracked prices
python main.py list                                         # watchlist with low/high
python main.py remove 1
python -m pytest                                            # tests
```

Run `check` once or twice a day (cron on Linux/Mac, Task Scheduler on Windows) to build price history.

## Optional: turn on the LLM (free)

1. Get a free key from [Groq](https://console.groq.com) (or any OpenAI-compatible provider, e.g. Gemini's OpenAI endpoint).
2. `export LLM_API_KEY=your_key`
   Optional: `LLM_BASE_URL`, `LLM_MODEL` (defaults: Groq, `llama-3.1-8b-instant`).

With a key you can type `"cheap earbuds below Rs 1500"`; the LLM extracts the query and budget, and writes a 3-line summary. Without a key a regex does the parsing and the summary is skipped.

## Architecture

```
main.py (CLI / agent loop)
  ├── llm.py        optional: request parsing + grounded summary (OpenAI-compatible API)
  ├── providers.py  Flipkart / Amazon / Demo -> list[Product]; cache + rate limit
  ├── ranking.py    similarity, cheaper-alternative scoring, deal verdict
  └── store.py      SQLite: watchlist + price_history
```

Flow for `search`: parse request -> fetch from each provider -> pick best match -> filter cheaper candidates -> rank -> (optional) LLM summary.

### Design decisions (good interview talking points)

- **Tools + reasoning split.** Data fetching, ranking and storage are deterministic Python. The LLM only handles language (parsing and summarising) and is given the computed facts, so it cannot invent prices. If the LLM fails, the agent still works.
- **Provider interface.** Each source implements `search(query) -> list[Product]`. Adding a new store means one new class.
- **Explainable ranking.** `score = similarity * (0.5 + saving) * rating_factor`. Similarity blends token overlap (Jaccard) with fuzzy string matching (`difflib`). Items rated below 3.5 are dropped; unrated items are kept but penalised.
- **Price history, not MRP.** Indian sites show inflated MRPs, so the verdict compares the price with *its own history* (lowest seen, change since last check) and warns about very large MRP discounts.
- **Polite scraping.** 3 s gap per site, 30 min on-disk cache, one retry with backoff, and an immediate stop on 403/429/503. Detects Amazon CAPTCHA pages and skips the source instead of retrying.
- **Resilient parsing.** Flipkart's CSS class names are obfuscated and change often, so the parser uses stable cues (`data-id` cards, `/p/` links, image alt text, the ₹ sign). Amazon uses its `data-asin` result markup.
- **SQL design.** `watchlist` (unique URL) and `price_history` (foreign key, indexed on `watch_id, checked_at`).

## Limitations (be upfront about these)

- Scraping is best effort. Amazon.in often blocks plain requests (503/CAPTCHA), in which case you will only get Flipkart results. Retailers' terms of service restrict automated access, so this is for personal, low-volume use.
- "Similar" is text similarity, not true product matching (no model numbers or specs comparison).
- Offers (bank discounts, coupons) are not parsed, only listed price vs MRP.

## Ideas to extend

- Email / Telegram alerts when a target is hit
- Add Croma, Myntra or a price-API provider
- Use LangChain tool-calling so the LLM chooses which tool to run
- Small Streamlit UI on top of `ranking.py`

# Your shopping helper: LangChain walkthrough

## The idea

Think of each shopping function as a small service, like a Lambda function with a defined input and output. LangChain exposes those functions as tools. The LLM chooses which service to call. Python still fetches, filters and calculates the facts.

A fixed workflow always runs the same steps. An agent can choose its next step after seeing the last tool result. Our runtime is `langchain.agents.create_agent`, which builds a model/tool loop on LangGraph. This project uses that runtime; it does not claim a separately designed custom LangGraph workflow.

## The three tools

1. `search_products(query, max_price)`: calls the existing provider classes and returns product dictionaries. It filters budgets in code. Sources come from the UI, not the model.
2. `compare_products(query, max_price)`: reuses best_match and find_alternatives from ranking.py. It computes savings with subtraction. "Similar" means text similarity, not verified specs.
3. `price_history(watch_id)`: reads the saved SQLite observations and stats. It cannot create a watch or fetch fresh prices. The timestamp shows when each observation was saved.

The `@tool` decorator gives the model each function's name, description and argument schema. Type hints such as `watch_id: int` let LangChain validate the arguments before calling Python.

## What happens when you ask

For "Compare earbuds under 2000":

- Your text reaches run_shopping_agent.
- With a key, ChatOpenAI uses the configured OpenAI-compatible endpoint. The model receives the tool descriptions and the request.
- It can return a structured tool call, for example compare_products with query "earbuds" and max_price 2000.
- LangChain validates the arguments and runs Python. Python gets listings and ranks alternatives.
- A ToolMessage carries the result back to the model. It may request another tool, or finish without another call.
- Our UI displays only recorded tool facts. It does not display the model's final prose. That stops generated answer text from supplying fake prices or savings.

Product titles can still contain bad or misleading content, and scraped data can be wrong. This design reduces risk; it does not make the whole app hallucination-proof or injection-proof.

## No key or failed model

There is no model-based agent without a key. Simple rules recognise budgets, comparison words and history requests. If tool calling fails or the model returns no tool facts, the app says it is using rules. This is useful degradation, not hidden AI reasoning.

## Files to read, in order

1. providers.py: Product dataclass and provider search interfaces.
2. ranking.py: similarity, cheaper alternatives and deal verdict.
3. store.py: watchlist, history, SQLite stats.
4. agent.py: ShoppingSession, the three decorated tools, create_agent invocation, fallback and render_answer.
5. test_agent.py: a scripted model sends tool calls through the actual LangChain loop, including a deliberately fake final price that must never reach the UI.

## Why the safeguards exist

- Python enforces a recognised request budget even if the model tries to raise it.
- A six-call cap and graph limit stop endless loops.
- Timeouts and no automatic model retries reduce surprise requests.
- A per-request cache avoids repeated identical provider searches.
- Tools are read-only. There is no purchase, arbitrary URL fetch or watchlist mutation tool.
- SQLite history is copied on the caller thread before LangChain runs tools on workers, avoiding cross-thread SQLite errors.
- Keys belong in server environment/secrets, not source code. The normal agent sends the request and shopping/history tool results to the selected model provider.

## An honest interview description

"I extended a Python shopping helper with a LangChain tool-calling layer. I wrapped product search, cheaper-alternative comparison and SQLite price history as typed tools. The model chooses tools based on a natural-language request, while fetching, ranking, budgets and savings stay deterministic. I display tool records rather than model-written price claims, and added a no-key fallback and bounded execution. I verified the orchestration locally using a scripted model and offline data."

Only call the model provider integration live-tested once you have actually tested it with a tool-capable model. Do not call this production retail automation, RAG, multi-agent coordination or an autonomous purchasing agent. Adding this code does not establish LangChain production experience at Accenture.

## Test status and practical limits

The local checks cover a two-step LangChain loop, schemas, budgets, savings, saved history, errors, loop limits, no-key mode and a Streamlit interaction. They do not prove a real model picks the right tool every time. No real model API inference was called, no current retailer availability was tested, and these changes have not been pushed or deployed.

Amazon can block scraping. Demo prices are sample data. Watchlists can disappear on free-host restarts. Existing hosted SQLite is not a per-user private database. There are no automatic alerts, purchases or background price checks.

## Try these after approval/deployment

- Without a key: "earbuds under 1000", "compare earbuds under 2000", "history watch 1".
- With a tool-capable model configured: try those same requests, inspect Tool facts, and confirm the mode says langchain.
- Try a missing watch and an impossible budget. Explain why an empty result is better than a made-up answer.
- Change one tool description and see whether the model selects it differently. Keep prices and authority outside the model.

## References

- https://docs.langchain.com/oss/python/langchain/agents
- https://docs.langchain.com/oss/python/integrations/chat/openai

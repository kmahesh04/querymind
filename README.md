# QueryMind: ask an e-commerce database in plain English

QueryMind turns a plain-English question into a SQL query, checks it for safety, runs it on a read-only copy of the store's database, and explains the result. It is built for the AI Engineering Bootcamp capstone (Text-to-SQL assignment).

Example:

> **You:** How many orders were shipped to Austin?
>
> **QueryMind:** The answer is 272. *Assumption: "shipped to" uses the order's shipping city, not the customer's home city.*

## Why e-commerce

Order tracking is a question everyone already understands, from Amazon, Flipkart and similar stores. The data also needs real joins: orders, items, products, categories, shipments, payments, returns, reviews, and tags. That makes it a fair test of Text-to-SQL, with realistic traps such as "customers in Austin" (home city) versus "orders shipped to Austin" (shipping city).

## How it works

```
question
  -> 1. classifier         rules block write requests; a model labels off-topic questions
  -> 2. schema linker      keyword match picks the tables, plus their foreign-key neighbours
  -> 3. example retriever  vector search (Gemini embeddings) finds the 4 most similar examples
  -> 4. SQL generator      Gemini writes one SELECT from the schema and examples (Grok if Gemini fails)
  -> 5. SQL validator      one SELECT only, known tables only, SQLite planner check, row cap
  -> 6. executor           read-only connection, 3-second timeout, 100-row cap
  -> 7. explainer          a sentence and the table; any assumption is stated
```

If the validator rejects the SQL, the generator gets one retry with the reason. If that also fails, the user sees an honest message and the SQL that was attempted.

The UI (Streamlit) calls the FastAPI backend over HTTP. The backend calls the pipeline. The pipeline is the only part that talks to the model providers.

Safety is enforced in code, not left to the model:
- Write requests (delete, drop, update, and similar) are refused before any model is called.
- The validator accepts one `SELECT` or `WITH` statement and blocks data-changing keywords.
- The database connection is opened read-only, so even a bypassed validator cannot write.
- Every answer is logged to `data/query_log.jsonl` with its SQL, status and timing.

## Key design decisions

- **Vector search for examples, with TF-IDF as a fallback.** Paraphrased questions are matched by meaning, which keyword matching misses. Without a Gemini key, the TF-IDF retriever keeps the app working.
- **Gemini 3.8 Flash as the default model, with Grok as an optional fallback.** The provider is set by `LLM_PROVIDER`. The other provider is used only if the first call fails, so a quota problem does not stop the app.
- **SQLite's own planner as the validator.** `EXPLAIN` checks the SQL against the real database, with no extra parser to install.
- **A read-only database connection.** Even if the validator were bypassed, the connection cannot write.
- **FastAPI backend with a Streamlit UI.** The UI only calls the API over HTTP, so another client can reuse the same backend.

## Setup

Requirements: Python 3.11 or newer and a Gemini API key from Google AI Studio. A Grok API key from xAI is optional, as a fallback.

```bash
cd querymind
pip install -r requirements.txt
cp .env.example .env          # then put your key after GEMINI_API_KEY=
```

The database is already included (`data/shop.db`). To rebuild it from scratch:

```bash
python -m db.seed
```

## Run it

Two terminals, both in the `querymind` folder:

```bash
# Terminal 1: the API
uvicorn api.main:app --reload

# Terminal 2: the Streamlit app
streamlit run app/streamlit_app.py
```

Open the Streamlit address it prints (usually http://localhost:8501). The admin page is in the sidebar under "Admin". The API's own documentation is at http://localhost:8000/docs.

## Sample questions

| Question | Type |
|---|---|
| How many orders are in each status? | aggregate |
| Revenue in September 2026 | date |
| Which 5 products sold the most units? | join |
| Average delivery time in days for each carrier | date |
| How many customers live in Austin? | ambiguity (home city) |
| How many orders were shipped to Austin? | ambiguity (shipping city) |
| Which customers have never placed an order? | anti-join |
| Which tags appear on products in the Fiction category? | many-to-many |
| Delete all returns recorded in 2025 | refused (unsafe) |
| Write a short poem about shopping | refused (out of scope) |

## Evaluation

The eval set has 25 questions: 23 answerable and 2 that must be refused. Each answerable question has a hand-checked gold SQL. A question passes when the generated SQL returns the same rows as the gold SQL, compared as a set so that equivalent queries count as correct.

Run it with:

```bash
python -m evals.run_eval
```

Progress is saved after each question, so if the free-tier quota runs out, the next run continues where it stopped.

**Results:** see `evals/results/report.md`. It lists accuracy by query type, the SQL for every failure, and the retrieval method and timing for each question.

### Latest run (22 October 2026)

Model: `gemini-3.8-flash`. Calls answered: Gemini 47, Grok 0, fallback 0. Grok was configured as an optional fallback but was never used in this run.

| Measure | Result |
|---|---|
| Overall | 24 / 25 (96%) |
| Answerable questions | 22 / 23 |
| Refusals correct | 2 / 2 |
| Queries that needed a retry | 0 |
| Median / slowest time | 6.9 s / 18.0 s |

By query type: aggregation 6/6, ambiguity 2/2, date 4/4, join 4/4, many-to-many 2/2, simple filter 3/3, having 1/2, unsafe refusal 1/1, out-of-scope refusal 1/1.

The one miss, q18 ("Which customers have placed at least 8 orders?"), returns the right customers and counts. It also adds the customer ID as a third column and sorts the output. The scorer compares column counts, so it is marked as a fail. This is a known limitation of the strict scorer, not a wrong answer.

The full per-question report is in `evals/results/report.md`.

## Data

Eleven tables: `customers`, `categories`, `products`, `tags`, `product_tags`, `orders`, `order_items`, `payments`, `shipments`, `returns`, `reviews`. The full dictionary, with every column explained, is in `docs/data_dictionary.md`.

The data is synthetic, generated by `db/seed.py` with a fixed random seed so results are repeatable. It covers 1,200 customers, 300 products and 5,000 orders from January 2025 to September 2026.

## Tests

```bash
python tests/test_pipeline.py        # 32 tests: safety, retrieval, pipeline flow, explanation
python tests/test_eval_harness.py    # 8 tests: the eval scorer itself
python tests/test_llm_routing.py     # 6 tests: provider order, fallback, missing keys
```

These tests need no API key. They use a fake model where a model is needed.

## Security

- **Sign-in with roles.** Each role has its own password in `.env`: `APP_PASSWORD_CEO`, `APP_PASSWORD_MANAGER` and `APP_PASSWORD_BA`. The password decides the role, and the API checks it on every data request.
- **Role access.**
  - **CEO:** every table, with full names and emails.
  - **Manager:** operations tables. No customers, no payments, no customer IDs, no refund amounts.
  - **BA:** products, orders, shipments and reviews. No customers, no payments, no returns, no customer IDs.
  - Access is enforced by SQLite's authorizer, which checks each table and column a query touches. This works even through joins, subqueries and `COUNT(*)`. The model also sees only the tables its role may read.
- **Personal data is masked** for every role except the CEO. Customer names become `K*** S***`, emails become `k***@domain`, and phone or address columns are hidden. Masking happens in the API before answers are returned or logged.
- **The admin page** is for the CEO role only.
- **Read-only access.** The connection cannot write, and the validator accepts only one SELECT.

These protect a demo. A production version would move to PostgreSQL with database-level roles, add individual user accounts, and add rate limits.

## Limitations

- **Two providers.** Gemini writes the SQL and provides the embeddings. Grok is an optional fallback, set with `LLM_PROVIDER` and a key. All model calls live in one file (`pipeline/llm.py`), so swapping a provider touches only that file.
- **Quotas.** Gemini's free-tier quotas are small and reset daily. Grok is billed per token in the xAI Console. A full eval run takes many requests, so it may need more than one session.
- **Read-only, single database.** QueryMind does not write data, and it works on one SQLite database, not a warehouse.
- **Ambiguous questions.** Where a question could mean two things, QueryMind picks one and says so. It does not ask a follow-up question.
- **Small few-shot bank.** The 35 examples cover the common patterns. Questions far outside them are more likely to fail.
- **Summaries are checked, not perfect.** The AI summary is used only when every number in it appears in the result rows. Otherwise the template summary is shown.
- **Not a security boundary for production.** The read-only connection and validator are good practice, but a real deployment would also need authentication and per-user permissions.

## Project structure

```
querymind/
  db/            schema.sql, seed.py
  data/          shop.db, examples.json
  pipeline/      classify, linker, examples, generate, validate_sql, execute, explain, engine, llm
  api/           FastAPI routes
  app/           Streamlit query page and admin page, API client
  evals/         eval_set.json, harness, runner, results
  tests/         pipeline and eval-harness tests
  docs/          data_dictionary.md
```
